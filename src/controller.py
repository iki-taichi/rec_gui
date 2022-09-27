# coding: utf-8
# Controller for RecVNC
#
# 2022-09 
# Taichi Iki
#


import os

import re
import json
import yaml
import base64
import time
import datetime
import asyncio
import threading
import numpy as np

import PIL.Image
import requests
import tornado.web
import tornado.escape
import tornado.template
import selenium.webdriver
from selenium.webdriver.common.keys import Keys

from vnc_proxy import CustomVNCLoggingServerFactory, CustomVNCLoggingServerProxy
from twisted.internet import reactor

import serializer

DEFAULT_DISPLAY = ':1.0'
os.environ['DISPLAY'] = DEFAULT_DISPLAY

CONTROLLER_PORT = 8888
VNC_SERVER_PORT = 5900
VNC_PUBLIC_PORT = 5902
URL_PREFIX = f'http://localhost:{CONTROLLER_PORT}'

RECORDS_DIR_PATH = '/files/records'
CONVERTED_DIR_PATH = '/files/converted'
TASKS_DIR_PATH = '/files/tasks'
WEBUI_DIR_PATH = '/files/webui'
COMPONENTS_DIR_PATH = '/files/components'

WELCOME_PAGE_NAME = 'welcome.html'
THANKS_PAGE_NAME = 'thanks.html'


class ControllerConfig(object):
    
    @staticmethod
    def _bool(x):
        # ad hoc conversion
        if isinstance(x, bool):
            return x
        else:
            try:
                return float(x) != 0
            except:
                if isinstance(x, str):
                    return x.strip().lower() in ('true', 't')
                else:
                    return False
    
    def __init__(self,
        do_recording = True,
        screenshot_interval = 0.1,
        script_rule_name = 'script_rule.js',
        task_sequence_name = 'default_tasks.yml'
    ):
        self.do_recording = self._bool(do_recording)
        self.screenshot_interval = float(screenshot_interval)
        self.script_rule_name = script_rule_name
        self.task_sequence_name = task_sequence_name

    def get_description(self):
        return [
            ('do_recording', self.do_recording),
            ('screenshot_interval', self.screenshot_interval),
            ('script_rule_name', self.script_rule_name),
            ('task_sequence_name', self.task_sequence_name),
        ]
        
    @property
    def script_rule_path(self):
        return os.path.join(COMPONENTS_DIR_PATH, self.script_rule_name)
    
    @property
    def task_sequence_path(self):
        return os.path.join(TASKS_DIR_PATH, self.task_sequence_name)
    
    @property
    def welcome_page_path(self):
        return os.path.join(COMPONENTS_DIR_PATH, WELCOME_PAGE_NAME)
    
    @property
    def thanks_page_path(self):
        return os.path.join(COMPONENTS_DIR_PATH, THANKS_PAGE_NAME)


class ScriptInjectionRule(object):
    """Holds a set of script injection rule that will be executed 
    after an HTML page is loaded if the url matches a rule"""
    
    @staticmethod
    def read_scripts(file_path):
        
        scripts = []
        matcher = None
        line_buffer = []
        
        with open(file_path) as f:
            lines = f.readlines()
        
        for line in lines:
            if line.startswith('//!'):
                if matcher is not None:
                    scripts.append((matcher, ''.join(line_buffer)))
                    line_buffer.clear()
                matcher = re.compile(line[3:].rstrip('\n'))
            else:
                line_buffer.append(line)
        if matcher is not None and len(line_buffer) > 0:
            scripts.append((matcher, ''.join(line_buffer)))
        
        return scripts

    def __init__(self, file_path):
        
        self.file_path = file_path
        self.reload()
        
    def reload(self):
        
        if self.file_path is not None:
            self.script_injection_rule = self.read_scripts(self.file_path)
        else:
            self.script_injection_rule = []
    
    def get_description(self):
        
        return [(m.pattern, s) for m, s in self.script_injection_rule]
    
    def apply(self, driver, url, task_env):
        
        for matcher, script in self.script_injection_rule:
            if matcher.search(url):
                t = tornado.template.Template(script)
                driver.execute_script(t.generate(**task_env).decode('utf8'))
                print('applied:', matcher, url)
        

class TaskSequence(object):
    """Represents task sequence used in a recording."""
    
    @staticmethod
    def get_value(var_name, var_def, random_state, update):
    
        def _eval(var_def, random_state):
            
            if var_def is None:
                return None
            
            _type = var_def[0]
            if _type == '=':
                # constant string
                return var_def[1:]
            
            elif _type == '$':
                # random variable
                func, args = re.findall('^\$([^()]+)\((.+)\)', var_def)[0]
                args = [_.strip() for _ in args.split(',')]
                
                if func == 'int':
                    
                    lb = np.iinfo(np.int32).min if args[0] == 'None' else int(args[0])
                    ub = np.iinfo(np.int32).max if args[1] == 'None' else int(args[1])
                    return random_state.randint(lb, ub)
            
                elif func == 'choice':
                    
                    return random_state.choice(args)
                
                raise RuntimeError(f'unknown random function: {func}')
        
        # we evaluate var_def even if update includes var_name
        # to keep random state order
        v = _eval(var_def, random_state)
        if var_name in update:
            v = _eval(update[var_name], random_state)
        
        return v
    
    @classmethod
    def validate_variables(cls, envs, tasks):
        random_state = np.random.RandomState(0)
        update = {}
        try:
            for env in envs.values():
                for k, v in env['variables'].items():
                    cls.get_value(k, v, random_state, {})
            for task in tasks:
                for k, v in task.get('update', {}).items():
                    cls.get_value(k, v, random_state, {})
        except Exception as e:
            return False
        return True
    
    def __init__(self, file_path):
        
        self.file_path = file_path
        self.reload()
    
    def reload(self):
        
        y = yaml.safe_load(open(self.file_path))
        
        assert 'task_set' in y or 'task_seq' in y, 'file should contain task_set or task_seq.'
        assert not('task_set' in y and 'task_seq' in y), 'file should not contain both of task_set and task_seq.'
        assert 'total_time_limit' in y, 'file should contain total_time_limit.'
        
        self.total_time_limit = y['total_time_limit']
        self.random_seed = y.get('random_seed', None)
        self.use_random_state = (self.random_seed is not None)
        
        self.envs = y.get('envs', [])
        
        self.is_set = 'task_set' in y
        if self.is_set:
            self.tasks = y.get('task_set', [])
        else:
            self.tasks = y.get('task_seq', [])
        
        assert self.validate_variables(self.envs, self.tasks)
        
        self.gen = None
        self.current_task = None
    
    def get_description(self):
        
        return [
            ('total_time_limit', self.total_time_limit),
            ('is_set', self.is_set),
            ('random_seed', self.random_seed),
            ('envs', self.envs),
            ('tasks', self.tasks),
        ]
    
    def __iter__(self):
        
        random_state = None
        if self.use_random_state:
            random_state = np.random.RandomState(self.random_seed)
        
        def eval_variables(task):
            
            env = self.envs[task['env']]
            update = task.get('update', {})
            return {k: self.get_value(k, v, random_state, update) for k, v in env['variables'].items()}
        
        if self.is_set:
            # tasks with sampling 
            while True:
                task_id = random_state.randint(0, len(self.tasks))
                task = self.tasks[task_id]
                variables = eval_variables(task)
                url = tornado.template.Template(task['url']).generate(**variables).decode()
                yield {'task_id': task_id, 'url': url, 'variables': variables}
        else:
            # sequential tasks
            for task_id, task in enumerate(self.tasks):
                variables = eval_variables(task) 
                url = tornado.template.Template(task['url']).generate(**variables).decode()
                yield {'task_id': task_id, 'url': url, 'variables': variables}
    
    def reset(self):
        
        self.gen = iter(self)
    
    def get_next(self):
        
        self.current_task = next(self.gen)
        return self.current_task

    
class DriverWrapper(object):
    """A wrapper class for selenium Chrome driver"""
    
    def __init__(self):
        
        self.driver = None
        
    def is_browser_alive(self):

        try:
            self.driver_wrapper.driver.window_handles
        except:
            return False
        
        return True
    
    def init_driver(self):
        
        option_str = '--no-sandbox --disable-gpu --disable-setuid-sandbox --kiosk'
        options = selenium.webdriver.ChromeOptions()
        for o in option_str.split(' '):
            options.add_argument(o)
        options.add_experimental_option('excludeSwitches', ['enable-automation'])

        self.driver = selenium.webdriver.Chrome('/chromedriver', options=options)

    def go(self, url, script_rule=None, task_env={}):
        
        if not self.is_browser_alive():
            self.init_driver()
        
        self.driver.get(url)
        
        if script_rule:
            script_rule.apply(self.driver, url, task_env)


class EventWriter(object):
    """VNC proxy and http server write events through this class."""
    
    def __init__(self):
    
        self.running = False
        self.path = None
        self.default_data = {}
    
    def write(self, s):
        
        with open(self.path, 'a') as f:
            print(s, file=f)
    
    def set_default(self, name, data):
        
        self.default_data[name] = data
    
    def start(self):
        
        data = {
            'time': time.time(),
            'event': 'start',
            'args': [self.default_data],
        }
        self.write(json.dumps(data))
        self.running = True
    
    def stop(self, args={}):
        
        self.running = False
        data = {
            'time': time.time(),
            'event': 'stop',
            'args': [{'stop_args': args}],
        }
        self.write(json.dumps(data))
    
    def __call__(self, s):
       
        if self.running and self.path:
            self.write(s)
    

class RecordingThared(threading.Thread):
    """Records screenshots with grabscreen_x11. 
    We use a sub thread to take screenshots."""
    
    @staticmethod
    def xgrab(xdisplay=DEFAULT_DISPLAY):
    
        size, data = PIL.Image.core.grabscreen_x11(xdisplay)
        return PIL.Image.frombytes("RGB", size, data, "raw", "BGRX", size[0] * 4, 1)

    def __init__(self, stop_event, interval, working_dir_path, writer, 
                 do_recording=True, duration=None, after_auto_stop=None, stop_args={}):
        
        super().__init__()
        self.stop_event = stop_event
        self.interval = interval
        self.working_dir_path = working_dir_path
        self.writer = writer
        self.do_recording = do_recording
        self.duration = duration
        self.after_auto_stop = after_auto_stop
        self.stop_args = stop_args

    def run(self):
        
        auto_stop_timer = None
        if self.duration is not None:
            def auto_stop():
                self.stop_event.set()
                print('recording stopped by auto_stop')
                if self.after_auto_stop:
                    self.after_auto_stop()
                    print('triggered after_auto_stop')
            auto_stop_timer = threading.Timer(self.duration, auto_stop)
            auto_stop_timer.start()
        
        if self.do_recording:
        
            self.writer.path = os.path.join(self.working_dir_path, 'events.txt')
            self.writer.start()
            
            elapsed = 0
            while not self.stop_event.wait(max(0, self.interval - elapsed)):
                t_start = time.time()
                image = self.xgrab()
                path = os.path.join(self.working_dir_path, f'{time.time()}.jpg')
                image.save(path)
                elapsed = time.time() - t_start
        
            self.writer.stop(self.stop_args)
        
        else:
            
            while not self.stop_event.wait(self.interval):
                pass
        
        if auto_stop_timer:
            auto_stop_timer.cancel()


class TornadoThread(threading.Thread):
    """Tornado runs in a sub thread to use twisted and tornado in a process."""
    
    def __init__(self, writer, config):

        super().__init__()
        self.writer = writer
        self.config = config
        self.stop_event = None

    def run(self):

        asyncio.run(self.main())

    async def main(self):
        
        app = Application(self.writer, self.config)
        app.listen(CONTROLLER_PORT)
        self.stop_event = asyncio.Event()
        await self.stop_event.wait()
        

class CustomVNCLoggingServerProxyEx(CustomVNCLoggingServerProxy):
    """Customized VNC Proxy (client -> server side)
    This class adds actions that shows pages after making a connection"""
    
    def connectionMade(self):
        
        super().connectionMade()
        requests.get(URL_PREFIX+'/task/welcome')
    
    def connectionLost(self, reason):
        
        super().connectionLost(reason)
        requests.get(URL_PREFIX+'/grab/stop')


# In the following, we define the web server and the handlers.
class Application(tornado.web.Application):
    
    @staticmethod
    def get_default_prefix():
        
        return datetime.datetime.now().strftime('rec-%Y-%m-%dT%H%M%S')
    
    def __init__(self, writer, config):
        
        self.writer = writer
        self.driver_wrapper = DriverWrapper()
        
        self.config = None
        self.set_config(config)
        
        self.grab_stop = threading.Event()
        self.grab_stop.set()
        
        handlers = [
            # global functions
            (r"/reload", ReloadHandler),
            (r"/convert", ConvertHandler),
            # webui
            (r"/webui/(.*)", WebUIHandler),
            (r"/static/(.*)", tornado.web.StaticFileHandler, {
                'path': CONVERTED_DIR_PATH, 
            }),
            # task
            (r"/task/(.*)", TaskHandler),
            # grab
            (r"/grab/(.*)", GrabHandler),
        ]
        settings = dict(
            debug=True,
        )
        super().__init__(handlers, **settings)
    
    def set_config(self, config):
        
        self.task_sequence = TaskSequence(config.task_sequence_path)
        self.script_rule = ScriptInjectionRule(config.script_rule_path)
        self.config = config
    
    def start_recording_thread(self, interval, duration, prefix, after_auto_stop=None):
        
        print('start_recording_thread', interval, prefix, duration, after_auto_stop)
        
        if not self.grab_stop.is_set():
            return False
        
        self.grab_stop.clear()
        
        if self.config.do_recording:
            working_dir = os.path.join(RECORDS_DIR_PATH, prefix)
            if not os.path.exists(working_dir):
                os.mkdir(working_dir)
        else:
            working_dir = None
        
        thread = RecordingThared(
            self.grab_stop,
            interval=interval,
            working_dir_path=working_dir,
            writer=self.writer,
            do_recording = self.config.do_recording,
            duration=duration,
            after_auto_stop=after_auto_stop,
            stop_args=dict(self.config.get_description()),
        )
        thread.start()
        return True
    
    def stop_recording_thread(self):
        
        print('stop_recording_thread')
        
        self.grab_stop.set()
    
    def move_to_welcome_page(self):
        
        file_path = self.config.welcome_page_path
        t = tornado.template.Template(''.join(open(file_path).readlines()))
        html = t.generate(**self.get_global_envs())
        self.driver_wrapper.go('data:text/html;base64,'+base64.b64encode(html).decode("ascii"))
    
    def move_to_thanks_page(self):
        
        file_path = self.config.thanks_page_path
        t = tornado.template.Template(''.join(open(file_path).readlines()))
        html = t.generate(**self.get_global_envs())
        self.driver_wrapper.go('data:text/html;base64,'+base64.b64encode(html).decode("ascii"))
    
    def get_global_envs(self):
        
        return {
            'total_time_limit': self.task_sequence.total_time_limit,
            'interval': self.config.screenshot_interval,
            'do_recording': self.config.do_recording,
            'url_prefix': URL_PREFIX,
        }
        

class TaskHandler(tornado.web.RequestHandler):
    
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with")
        self.set_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
    
    def get(self, cmd):
        
        if cmd == 'go':
            self.get_go()
        elif cmd == 'welcome':
            self.get_welcome()
        elif cmd == 'thanks':
            self.get_thanks()
        elif cmd == 'start_sequence':
            self.get_start_sequence()
        elif cmd == 'start_episode':
            self.get_start_episode()
        elif cmd == 'end_episode':
            self.get_end_episode()
        else:
            self.write(f'unknown: {cmd}')
        
    def get_go(self):
        
        url = self.get_argument('url', 'data:text/html, <html contenteditable>')
        
        print('task_go', url)
        
        driver_wrapper = self.application.driver_wrapper
        driver_wrapper.go(url, script_rule=self.application.script_rule)
        
        self.write(url)
        
        data = {
            'time': time.time(),
            'event': 'task',
            'args': [{'task_args': ['go', url]}],
        }
        self.application.writer(json.dumps(data))
    
    def get_welcome(self):
        
        self.application.move_to_welcome_page()
        self.write('done')
        
    def get_thanks(self):
        
        self.application.move_to_thanks_page()
        self.write('done')
    
    def _move_to_next(self):
        
        try:
            task = self.application.task_sequence.get_next()
        except Exception as e:
            self.application.stop_recording_thread()
            raise e
        
        task_env = self.application.get_global_envs()
        task_env.update(task['variables'])
        
        # ToDo: this may block if the origin of url is this controller
        self.application.driver_wrapper.go(
            task['url'], 
            script_rule=self.application.script_rule, 
            task_env=task_env
        )
        
        # write event
        data = {
            'time': time.time(),
            'event': 'task',
            'args': [{'task_args': ['move_to_next', task['url']]}],
        }
        self.application.writer(json.dumps(data))
    
    def get_start_sequence(self):
        
        # start grab
        interval = self.application.config.screenshot_interval
        duration = self.application.task_sequence.total_time_limit
        prefix = self.application.get_default_prefix()
        ret = self.application.start_recording_thread(
                interval, duration, prefix, after_auto_stop=self.application.move_to_thanks_page)
        if not ret:
            self.write('failed to start recording')
            return
        
        # move to the first task
        self.application.task_sequence.reset()
        
        # write event
        data = {
            'time': time.time(),
            'event': 'task',
            'args': [{'task_args': ['start_sequence']}],
        }
        self.application.writer(json.dumps(data))
        
        # move to the first task
        try:
            self._move_to_next()
        except StopIteration:
            self.get_thanks()
        except Exception as e:
            print(e)
            self.write(str(e))
            return
        
        self.write('done')
        
    def get_start_episode(self):
        
        task = self.application.task_sequence.current_task
        task_args = ['start_episode', task['url'], task['variables']]
        data = {
            'time': time.time(),
            'event': 'task',
            'args': [{'task_args': task_args}],
        }
        self.application.writer(json.dumps(data))
        
        print(task_args)
        
        self.write('done')
    
    def get_end_episode(self):
        
        reward = self.get_argument('reward', None)
        detail = self.get_argument('detail', None)
        if detail:
            detail = json.loads(tornado.escape.url_unescape(detail))
        task_args = ['end_episode', reward, detail]
        data = {
            'time': time.time(),
            'event': 'task',
            'args': [{'task_args': task_args}],
        }
        self.application.writer(json.dumps(data))
        
        print(task_args)
        
        try:
            self._move_to_next()
        except StopIteration:
            self.get_thanks()
        except Exception as e:
            print(e)
            self.write(str(e))


class GrabHandler(tornado.web.RequestHandler):
    
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with")
        self.set_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
    
    def get(self, cmd):

        if cmd == 'start':
            self.get_start()
        elif cmd == 'stop':
            self.get_stop()
        else:
            self.write(f'unknown: {cmd}')
    
    def get_start(self):
        
        interval = float(self.get_argument('interval', 0.1))
        prefix = self.get_argument('prefix', None)
        if prefix is None:
            prefix = self.application.get_default_prefix()
        duration = self.get_argument('duration', None)
        if duration is not None:
            duration = float(duration)
        
        ret = self.application.start_recording_thread(
            interval, duration, prefix, after_auto_stop=self.application.move_to_thanks_page)
        if ret:
            self.write('started')
        else:
            self.write('failed to start')    
    
    def get_stop(self):
        
        self.application.stop_recording_thread()
        self.write('stopped')


class ReloadHandler(tornado.web.RequestHandler):

    def get(self):
        
        config = self.get_argument('config', None)
        if config:
            config_dict = json.loads(tornado.escape.url_unescape(config))
            self.application.set_config(ControllerConfig(**config_dict))
            self.write('done')
        else:
            self.write('config is missing')


class ConvertHandler(tornado.web.RequestHandler):

    def get(self):
        
        name = self.get_argument('name', None)
        if name is None:
            self.write('record not found')
            return
        
        record_path = os.path.join(RECORDS_DIR_PATH, name)
        converted_path = os.path.join(CONVERTED_DIR_PATH, name)
        
        if not os.path.exists(record_path):
            self.write('record not found')
            return
        
        serializer.serialize(record_path, converted_path, 0.1)
        
        self.write('done')


class WebUIHandler(tornado.web.RequestHandler):

    def get(self, cmd):

        if cmd == 'index':
            self.get_index()
        elif cmd == 'settings':
            self.get_settings()
        elif cmd == 'records':
            self.get_records()
        elif cmd == 'preview':
            self.get_preview()
        else:
            self.write(f'unknown: {cmd}')
    
    def get_index(self):
        
        file_path = os.path.join(WEBUI_DIR_PATH, 'index.html')
        t = tornado.template.Template(''.join(open(file_path).readlines()))
        html = t.generate(**self.application.get_global_envs())
        self.write(html)
    
    def get_settings(self):
        
        kv = {
            'config': self.application.config.get_description(),
            'task_sequence': self.application.task_sequence.get_description(),
            'script_rule': self.application.script_rule.get_description(),
        }
        
        file_path = os.path.join(WEBUI_DIR_PATH, 'settings.html')
        t = tornado.template.Template(''.join(open(file_path).readlines()))
        html = t.generate(**kv)
        self.write(html)
    
    def get_records(self):
        
        records = []
        for name in sorted(os.listdir(RECORDS_DIR_PATH)):
            file_path = os.path.join(RECORDS_DIR_PATH, name)
            if os.path.isdir(file_path):
                converted_path = os.path.join(CONVERTED_DIR_PATH, name)
                is_converted = os.path.exists(converted_path)
                convert_button =  f'<button onclick="convert(\'{name}\')">convert</button>'
                if is_converted:
                    conversion_state = 'done'
                    preview_path = f'<a href="/webui/preview?name={name}">link</a>'
                else:
                    conversion_state = 'yet'
                    preview_path = ''
                records.append((name, convert_button, conversion_state, preview_path))
        
        env = self.application.get_global_envs()
        env['records'] = records
        
        file_path = os.path.join(WEBUI_DIR_PATH, 'records.html')
        t = tornado.template.Template(''.join(open(file_path).readlines()))
        html = t.generate(**env)
        self.write(html)
    
    def get_preview(self):
        
        name = self.get_argument('name', None)
        if name is None:
            self.write('record not found')
            return
        
        converted_path = os.path.join(CONVERTED_DIR_PATH, name)
        
        env = self.application.get_global_envs()
        env['name'] = name
        env['outputs'] = ''.join(open(os.path.join(converted_path, 'meta.json')).readlines())
        
        file_path = os.path.join(WEBUI_DIR_PATH, 'preview.html')
        t = tornado.template.Template(''.join(open(file_path).readlines()))
        html = t.generate(**env)
        self.write(html)

        
if __name__ == "__main__":
    
    writer = EventWriter()
    config = ControllerConfig()
    
    tornado_thread = TornadoThread(writer, config)
    tornado_thread.start()
    print('tornado_thread started')
    
    factory = CustomVNCLoggingServerFactory(
            host='localhost',
            port=VNC_SERVER_PORT,
            password_required=True,
            writer=writer,
            pseudocursor=True,
        )
    factory.protocol = CustomVNCLoggingServerProxyEx
    factory.listen_tcp(VNC_PUBLIC_PORT)
    print('reactor listen_tcp start')
    print('reactor will run')
    reactor.run()
    
    tornado_thread.stop_event.set()
    tornado_thread.join()
    print('tornado_thread joined')

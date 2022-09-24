# coding: utf-8
# Serializer for Recording data for RecVNC
#
# 2022-09 
# Taichi Iki
#
# ToDo: Split scripts into some files.
# This file includes many things currently: 
# key settings, event definitions, interval, recorddata 
# 

import os
import re
import json
import base64
import numpy as np
import PIL.Image


# Key settings
SPECIAL_KEYS = {
    '[BackSpace]':  0xff08,
    '[Tab]':        0xff09,
    '[Return]':     0xff0d,
    '[Escape]':     0xff1b,
    '[Insert]':     0xff63,
    '[Delete]':     0xffff,
    '[Home]':       0xff50,
    '[End]':        0xff57,
    '[PageUp]':     0xff55,
    '[PageDown]':   0xff56,
    '[Left]':       0xff51,
    '[Up]':         0xff52,
    '[Right]':      0xff53,
    '[Down]':       0xff54,
    '[F1]':         0xffbe,
    '[F2]':         0xffbf,
    '[F3]':         0xffc0,
    '[F4]':         0xffc1,
    '[F5]':         0xffc2,
    '[F6]':         0xffc3,
    '[F7]':         0xffc4,
    '[F8]':         0xffc5,
    '[F9]':         0xffc6,
    '[F10]':        0xffc7,
    '[F11]':        0xffc8,
    '[F12]':        0xffc9,
    '[F13]':        0xFFCA,
    '[F14]':        0xFFCB,
    '[F15]':        0xFFCC,
    '[F16]':        0xFFCD,
    '[F17]':        0xFFCE,
    '[F18]':        0xFFCF,
    '[F19]':        0xFFD0,
    '[F20]':        0xFFD1,
    '[ShiftLeft]':  0xffe1,
    '[ShiftRight]': 0xffe2,
    '[ControlLeft]':0xffe3,
    '[ControlRight]':0xffe4,
    '[MetaLeft]':   0xffe7,
    '[MetaRight]':  0xffe8,
    '[AltLeft]':    0xffe9,
    '[AltRight]':   0xffea,
    '[Scroll_Lock]':0xFF14,
    '[Sys_Req]':    0xFF15,
    '[Num_Lock]':   0xFF7F,
    '[Caps_Lock]':  0xFFE5,
    '[Pause]':      0xFF13,
    '[Super_L]':    0xFFEB,
    '[Super_R]':    0xFFEC,
    '[Hyper_L]':    0xFFED,
    '[Hyper_R]':    0xFFEE,
    '[KP_0]':       0xFFB0,
    '[KP_1]':       0xFFB1,
    '[KP_2]':       0xFFB2,
    '[KP_3]':       0xFFB3,
    '[KP_4]':       0xFFB4,
    '[KP_5]':       0xFFB5,
    '[KP_6]':       0xFFB6,
    '[KP_7]':       0xFFB7,
    '[KP_8]':       0xFFB8,
    '[KP_9]':       0xFFB9,
    '[KP_Enter]':   0xFF8D,
    '[ForwardSlash]':0x002F,
    '[BackSlash]':  0x005C,
    '[SpaceBar]':   0x0020,
}
SPECIAL_KEYS_REV = {v:k for k, v in SPECIAL_KEYS.items()}

LAYOUT_US_STANDARD = {
    # shifted key: physical key
    '~': '`',
    '!': '1',
    '@': '2',
    '#': '3',
    '$': '4',
    '%': '5',
    '^': '6',
    '&': '7',
    '*': '8',
    '(': '9',
    ')': '0',
    '_': '-',
    '+': '=',
    'Q': 'q',
    'W': 'w',
    'E': 'e',
    'R': 'r',
    'T': 't',
    'Y': 'y',
    'U': 'u',
    'I': 'i',
    'O': 'o',
    'P': 'p',
    '{': '[',
    '}': ']',
    '|': '\\',
    'A': 'a',
    'S': 's',
    'D': 'd',
    'F': 'f',
    'G': 'g',
    'H': 'h',
    'J': 'j',
    'K': 'k',
    'L': 'l',
    ':': ';',
    '"': '\'',
    'Z': 'z',
    'X': 'x',
    'C': 'c',
    'V': 'v',
    'B': 'b',
    'N': 'n',
    'M': 'm',
    '<': ',',
    '>': '.',
    '?': '/',
}


# Event definitions
# - EventBase
#     - ControlEvent
#         - StartEvent
#         - StopEvent
#         - NewTaskEvent?
#     - CursorEvent
#     - ImageEvent
#     - PointerEvent
#     - KeyEvent
#     - ButtonEvent
#
class EventBase(object):
    
    name = 'base'
    repr_props = tuple()
    
    def __init__(self, time_abs, time_origin_abs, args):
        
        self.time_abs = time_abs
        self.time_origin_abs = time_origin_abs
        self.time_rel = time_abs - time_origin_abs
        self.args = args
    
    @property
    def timestamp(self):
        
        return f'{self.time_rel:.3f}'
        
    def __repr__(self):
        
        s = ', '.join(str(getattr(self, p)) for p in self.repr_props)
        return f'{self.name}({s})'


class ControlEvent(EventBase):
    
    name = 'control'
    
    def __init__(self, time_abs, time_origin_abs, args):
        
        super().__init__(time_abs, time_origin_abs, args)
        
        # make objects for sub arguments
        for k, v in args[0].items():
            if k == 'cursor':
                self.cursor = CursorHolder(*v)
            elif k == 'task_args':
                self.msg = v[0]
                self.subargs = v[1:]
            else:
                raise RuntimeError(f'unknown sub argument: {k}')
    

class StartEvent(ControlEvent):
    
    name = 'start'
                

class StopEvent(ControlEvent):
    
    name = 'stop'


class TaskEvent(ControlEvent):
    
    name = 'task'
    repr_props = ('msg', 'subargs')
    
    
class CursorHolder(object):
    
    def __init__(self, ox, oy, width, height, str_image, str_mask):
        
        self.ox = ox
        self.oy = oy
        self.size = (width, height)
        self.no_image = (width == 0) or (height == 0)
        if self.no_image:
            self.image = None
            self.mask = None
        else:
            self.image = PIL.Image.frombytes(
                'RGBX', self.size, 
                base64.b64decode(str_image.encode('utf-8'))
            )
            self.mask = PIL.Image.frombytes(
                '1', self.size, 
                base64.b64decode(str_mask.encode('utf-8'))
            )
        
    def draw(self, screen, position):
        
        output = screen.copy()
        if not self.no_image:
            p = (position[0] - self.ox, position[1] - self.oy)
            output.paste(self.image, p, self.mask)
        return output
    
    def __repr__(self):
        
        return f'cursor_holder({self.no_image}, {self.size})'
    

class CursorEvent(EventBase):
    
    name = 'cursor'
    repr_props = ('cursor',)
    
    def __init__(self, time_abs, time_origin_abs, args):
        
        super().__init__(time_abs, time_origin_abs, args)
        self.cursor = CursorHolder(*args)


class ImageEvent(EventBase):
    
    name = 'image'
    repr_props = ('basename',)
    
    @property
    def path(self):
        
        return self.args[0]
    
    @property
    def basename(self):
        
        return os.path.basename(self.args[0])
    
    @property
    def screen(self):
        
        return PIL.Image.open(self.path)
    

class PointerEvent(EventBase):
    
    name = 'pointer'
    repr_props = ('xy', 'button_mask')
    
    @property
    def x(self):
        
        return self.args[0]
    
    @property
    def y(self):
        
        return self.args[1]
    
    @property
    def xy(self):
        
        return (self.x, self.y)
    
    @property
    def button_mask(self):
        
        return self.args[2]


class KeyEvent(EventBase):

    name = 'key'
    repr_props = ('key_id', 'physical_key', 'logical_key', 'key_mask')
    key_layout = LAYOUT_US_STANDARD
    
    @property
    def key_id(self):
        
        return self.args[0]
    
    @property
    def logical_key(self):
        
        s = SPECIAL_KEYS_REV.get(self.args[0], None)
        if s is None:
            s = chr(self.args[0])
        return s
    
    @property
    def physical_key(self):
        
        s = SPECIAL_KEYS_REV.get(self.args[0], None)
        if s is None:
            s = chr(self.args[0])
            s = self.key_layout.get(s, s)
        return s
    
    @property
    def key_mask(self):
        
        return self.args[1]


# A virtual event
class ButtonEvent(EventBase):

    name = 'button'
    repr_props = ('button_id', 'event_type')
    
    @property
    def x(self):
        
        return self.args[0]
    
    @property
    def y(self):
        
        return self.args[1]
    
    @property
    def xy(self):
        
        return (self.x, self.y)
    
    @property
    def button_id(self):
        
        return self.args[2]
    
    @property
    def event_type(self):
        
        return self.args[3]


# Utility for interval
class Interval(object):
    """Holds a timestamp, input and actions for an interval"""
    
    def __init__(self, ge, lt):
        
        # timestamp
        self.ge = ge
        self.lt = lt
        # input
        self.image = None
        # outputs
        self.xy = None
        self.key_event = None
        self.button_event = None
        # control
        self.cursor_event = None
        self.control_events = None
        
    def __repr__(self):
        
        items = [
            f'[{self.ge:.3f}, {self.lt:.3f})', 
            self.image, 
            self.cursor_event, 
            self.xy, 
            self.key_event, 
            self.button_event, 
            self.control_events]
        return 'Interval({})'.format(', '.join(str(_) for _ in items))


class Intervals(object):
    """Manages Interval instances"""
    
    def __init__(self, boundaries):
        """boundaries: a list of float values that represent the boundaries of intervals by 'less than'.
        The float values will be sorted internally.
        We make an interval corresponds to all real value when an empty list is given for simplicity
        [] -> (-inf +inf)
        [X] -> (-inf X) [X +inf)
        [X, Y] -> (-inf X) [X Y) [Y +inf)
        """
        
        self.boundaries = sorted(boundaries)
        
        self.intervals = []
        last_lt = -float('inf')
        for lt in self.boundaries + [+float('inf')]:
            self.intervals.append(Interval(last_lt, lt))
            last_lt = lt
        
        self.finit_first_end = self.intervals[0].lt
        self.finit_last_end = self.intervals[-1].ge
        
        self.average_length = 1
        if len(self.intervals) >= 3:
            length = self.finit_last_end - self.finit_first_end
            self.average_length = length / (len(self.intervals) - 2)
    
    def __len__(self):
        """Returns the number of intervals in this class"""
        
        return len(self.intervals)
    
    def get_id(self, t):
        """Returns the corresponding interval id to the given float value t.
        None will be returned if t is greater than the last end of the intervals.
        """
        
        num_intervals = len(self.intervals)
        
        if num_intervals == 1:
            return 0
        
        if num_intervals == 2:
            return 0 if t < self.finit_first_end else 1
        
        if t >= self.finit_last_end:
            return num_intervals - 1
        
        i = round(t / self.average_length)
        i = max(1, min(i, num_intervals - 2))
        
        while True:
            # boundaries for the interval i
            ge_i = self.boundaries[i-1]
            lt_i = self.boundaries[i]
            if ge_i <= t and t < lt_i: 
                return i
            elif ge_i > t:
                i -= 1
                if i == 0:
                    return i
            else:
                # means t >= lt_i:
                i += 1
        
        return i
    
    def __getitem__(self, ids):
        
        num_intervals = len(self.intervals)
        
        def get_single(i):
            if i < 0 or i >= num_intervals:
                raise IndexError()    
            return self.intervals[i]
        
        if isinstance(ids, int):
            return get_single(ids)
        
        elif isinstance(ids, slice):
            return [get_single(i) for i in range(
                ids.start or 0, 
                min(num_intervals, ids.stop or num_intervals),
                ids.step or 1
            )] 
        
        return [get_single(i) for i in ids]
    
    def set_objects(self, objects, object_name, shift=True, take='first'):
        
        assert not (shift and take == 'all'), 'not supported the combination of shfit and take_all'
        
        # decide the type of objects: dict or event list 
        use_dict = False
        try:
            if 'time_rel' in objects[0] and 'obj' in objects[1]:
                use_dict = True
        except:
            pass
        
        interval_objects = [[] for _ in range(len(self.intervals))]
        if use_dict:
            for obj in objects:
                i = self.get_id(obj['time_rel'])
                interval_objects[i].append(obj['obj'])
        else:
            for obj in objects:
                i = self.get_id(obj.time_rel)
                interval_objects[i].append(obj)
            
        # Shift events to the previous steps so that each interval has at most an event.
        # We need this process because our model can handle just an event at an interval.
        # We choose this method to keep causarity.
        if shift:
            for i in reversed(range(len(interval_objects))):
                if len(interval_objects[i]) > 1:
                    if i != 0:
                        interval_objects[i-1] += interval_objects[i][:-1]
                    interval_objects[i] = [interval_objects[i][-1]]
        
        for i in range(len(interval_objects)):
            if interval_objects[i]:
                val = interval_objects[i]
                if take == 'first':
                    val = val[0]
                elif take == 'last':
                    val = val[-1]
                setattr(self.intervals[i], object_name, val)
    
    def set_defaults_with_neighbors(self, object_name, backward_first=True):
        
        if backward_first:
            preprocesses = (reversed, lambda x:x)
        else:
            preprocesses = (lambda x:x, reversed)
        
        for pp in preprocesses:
            last_item = None
            for interval in pp(self.intervals):
                item = getattr(interval, object_name)
                if item is None:
                    setattr(interval, object_name, last_item)
                else:
                    last_item = item
    

# Utility for recorded data
class RecordData(object):
    """Utility for recorded data"""
    
    event_classes = [StartEvent, StopEvent, CursorEvent, TaskEvent, ImageEvent, PointerEvent, KeyEvent]
    event_by_name = {cls.name:cls for cls in event_classes}
    
    num_buttons = 8
    click_types = ('click', 'double_click', 'triple_click')
    
    @staticmethod
    def _round(x):
        return int((x * 2 + 1) // 2)
    
    @staticmethod
    def is_acceptable_image_file(name):
        """Defines image files that this script can recognize"""
        
        return (not name.startswith('.')) and name.endswith('.jpg')
    
    @staticmethod    
    def read_jsonl(file_path):
        """Reads a jsonl file"""    
        
        with open(file_path) as f:
            return [json.loads(line) for line in f.readlines()]
    
    @staticmethod
    def pop_events_by_names(events, names):
        """Obtain popped events and the remained events. 
        Make sure this function breaks the original event list"""
        
        if isinstance(names, str):
            names = [names]
        
        popped_events = []
        for i in reversed(range(len(events))):
            if events[i].name in names:
                popped_events.append(events.pop(i))
        popped_events = list(reversed(popped_events))
        
        return popped_events, events
    
    @classmethod
    def make_event_objects(cls, raw_event_list, time_abs_min):
        """Obtains a list of event objects from a list of dict objects"""
        
        return [cls.event_by_name[ev['event']](
                time_abs=ev['time'],
                time_origin_abs=time_abs_min,
                args=ev['args'],
            ) for ev in raw_event_list]
    
    @classmethod
    def get_image_events(cls, base_dir, base_interval):
        """Obtains a list of image events, sorted by time, from a directory"""
        
        re_timestamp = re.compile('[.0-9]*[0-9]')
        
        events = []
        for name in os.listdir(base_dir):
            
            if cls.is_acceptable_image_file(name):
                
                m = re_timestamp.findall(name)
                if len(m) == 1:
                    
                    time_abs = float(m[0])
                    path = os.path.join(base_dir, name)
                    events.append({'time': time_abs, 'event': 'image', 'args': [path]})
        
        events.sort(key=lambda ev:ev['time'])
        time_abs_min = events[0]['time']
        
        events = cls.make_event_objects(events, time_abs_min)
        events = cls.fit_image_events(events, time_abs_min, base_interval)
        
        return events
    
    @classmethod
    def fit_image_events(cls, events, time_abs_min, base_interval, verbose=True):
        """fit image events so that each interval has exactly an event."""
        
        len_steps = cls._round(events[-1].time_rel / base_interval) + 1
        new_events = [None]*len_steps
        
        # Fill each step with the last image
        for ev in events:
            step_id = cls._round(ev.time_rel / base_interval)
            current_event = new_events[step_id] 
            if verbose and (current_event is not None):
                print(f'step={step_id}: {current_event} was removed due to redundancy.')
            new_events[step_id] = ev
        
        # Copy the previous step if a step is None
        for step_id in range(len_steps):
            if new_events[step_id] is None:
                time_rel = step_id*base_interval
                prev_ev = new_events[step_id-1]
                new_events[step_id] = cls.event_by_name[prev_ev.name](
                    time_abs=time_abs_min+time_rel,
                    time_origin_abs=time_abs_min,
                    args=prev_ev.args,
                )
                if verbose:
                    print(f'step={step_id}: previous step was copyied due to None.')
        
        return new_events
    
    @classmethod
    def split_masks(cls, x):
        return [bool(x & (1 << k)) for k in range(cls.num_buttons)]
    
    @classmethod
    def obtain_click_up_down_events(cls, pointer_events, unification_interval=None):
        """Returns event list.
        Each element is a dict with the following keys.
            - time_rel: timestamp for this event
            - obj:
                - event_type: event type in {click, up, down}
                - bid: related button mask in {0, 1, ..., num_buttons-1}
                - xy: the cursor position (x, y) 
        """
        
        make_event = lambda ev, bid, event_type: {
                'time_rel': ev.time_rel,
                'obj': ButtonEvent(
                    ev.time_abs, 
                    ev.time_origin_abs, 
                    [ev.x, ev.y, bid, event_type]
                )
        }
        
        if unification_interval is not None:
            is_continuous = lambda ev1, ev2: abs(ev2.time_rel - ev1.time_rel) <= unification_interval
        else:
            is_continuous = True
        
        button_events = [[] for _ in range(cls.num_buttons)]
        waiting_decision = [False] * cls.num_buttons
        
        last_ev = pointer_events[0]
        last_masks = cls.split_masks(pointer_events[0].button_mask)
        
        for i in range(1, len(pointer_events)):
        
            ev = pointer_events[i]
            masks = cls.split_masks(ev.button_mask)
        
            for bid, (l, lm) in enumerate(zip(masks, last_masks)):
                
                if l != lm:
                    if l:
                        # changed to down
                        waiting_decision[bid] = True
                    else:
                        # changed to up
                        if waiting_decision[bid]:
                            if is_continuous(last_ev, ev):
                                # issue click
                                button_events[bid].append(make_event(last_ev, bid, 'click'))
                            else:
                                # issue down and up
                                button_events[bid].append(make_event(last_ev, bid, 'down'))
                                button_events[bid].append(make_event(ev, bid, 'up'))
                        else:
                            # issue up
                            button_events[bid].append(make_event(ev, bid, 'up'))
                        
                        waiting_decision[bid] = False
                else:
                    if l:
                        # keeping down
                        if waiting_decision[bid]:
                            # issue down
                            button_events[bid].append(make_event(last_ev, bid, 'down'))
                    
                    waiting_decision[bid] = False      
            
            last_ev = ev
            last_masks = masks
        
        if unification_interval is not None:
            return cls.unify_clicks(button_events, unification_interval)
        return button_events
    
    @classmethod
    def unify_clicks(cls, event_list, interval):
    
        is_continuous_click = lambda ev, next_ev: \
            (next_ev is not None) and \
            (abs(next_ev['time_rel'] - ev['time_rel']) <= interval) and \
            (next_ev['obj'].event_type == 'click')
        
        unified_event_list = []
    
        for bid, _list in enumerate(event_list):
            _list.append(None)
            ev = _list.pop(0)
            while ev is not None:
                if ev['obj'].event_type == 'click':
                    event_type = cls.click_types[-1]
                    for i, event_type in enumerate(cls.click_types):
                        next_ev = _list.pop(0)
                        if not is_continuous_click(ev, next_ev):
                            event_type = event_type
                            break
                    unified_event_list.append({
                        'time_rel': ev['time_rel'],
                        'obj': ButtonEvent(
                            ev['obj'].time_abs, 
                            ev['obj'].time_origin_abs, 
                            [ev['obj'].x, ev['obj'].y, bid, event_type]
                        )
                    })
                    ev = next_ev
                else:
                    unified_event_list.append(ev)
                    ev = _list.pop(0)
    
        return unified_event_list
    
    def set_basic_properties(self, base_dir, base_interval, image_event_list):
        
        self.base_dir = base_dir
        self.event_log_path = os.path.join(base_dir, 'events.txt')
        self.base_interval = base_interval
        
        # We assume that image events have been sorted
        self.time_abs_min = image_event_list[0].time_abs
        self.time_abs_max = image_event_list[-1].time_abs
        self.time_elapsed = self.time_abs_max - self.time_abs_min
        
        self.base_image_path = image_event_list[0].path
        base_image = PIL.Image.open(self.base_image_path)
        self.image_size = base_image.size
        base_image.close()
    
    def get_extended_events(self):
        
        return self.make_event_objects(
            raw_event_list=self.read_jsonl(self.event_log_path),
            time_abs_min=self.time_abs_min,
        )
    
    def read_from_dir(self, base_dir, base_interval, click_max_interval=1/3):
        
        # Obtain image events from a directory
        image_events = self.get_image_events(base_dir, base_interval)
        
        # Set properties to self
        self.set_basic_properties(base_dir, base_interval, image_events)
        
        # Obtain other events than image events
        remained_events = self.get_extended_events()
        key_events, remained_events = self.pop_events_by_names(remained_events, 'key')
        pointer_events, remained_events = self.pop_events_by_names(remained_events, 'pointer')
        cursor_events, remained_events = self.pop_events_by_names(remained_events, 'cursor')
        control_events = remained_events
        
        # Add objects to the intervals
        self.intervals = Intervals([ev.time_rel for ev in image_events])
        self.intervals.set_objects(image_events, 'image', shift=False, take='first')
        
        # Key objects
        self.intervals.set_objects(key_events, 'key_event', shift=True, take='last')
        
        # Pointer objects
        # we consider mouse down and up event closer to 2 intervals as click
        button_events = self.obtain_click_up_down_events(pointer_events, unification_interval=click_max_interval)
        self.intervals.set_objects(button_events, 'button_event', shift=True, take='last')
        self.intervals.set_objects(
            [{'time_rel':ev.time_rel, 'obj':ev.xy} for ev in pointer_events], 
            'xy', 
            shift=False,
            take='last',
        )
        self.intervals.set_objects(
            [{'time_rel':ev['time_rel'], 'obj':ev['obj'].xy} for ev in button_events], 
            'xy', 
            shift=False,
            take='last',
        )
        self.intervals.set_defaults_with_neighbors('xy')
        
        # Cursor objects
        self.intervals.set_objects(cursor_events, 'cursor_event', shift=False, take='last')
        
        # Control objects
        self.intervals.set_objects(control_events, 'control_events', shift=False, take='all')
        
        # Set event data to the instance
        self.image_events = image_events
        self.key_events = sorted(key_events, key=lambda ev:ev.time_abs)
        self.pointer_events = sorted(pointer_events, key=lambda ev:ev.time_abs)
        self.cursor_events = sorted(cursor_events, key=lambda ev:ev.time_abs)
        self.control_events = sorted(control_events, key=lambda ev:ev.time_abs)
    
    def __init__(self, base_dir, base_interval):
        
        # members
        self.base_dir = None
        self.base_interval = None
        self.intervals = None
        self.base_image_path = None
        self.image_size = None
        self.time_abs_min = None
        self.time_abs_max = None
        self.time_elapsed = None
        
        self.image_events = None
        self.key_events = None
        self.pointer_events = None
        self.cursor_events = None
        self.control_events = None
        
        # read dara from a directory
        self.read_from_dir(base_dir, base_interval)        
    
    def __repr__(self):
        
        lines = [
            'RecordData:',
            f'    base_dir:{self.base_dir}',
            f'    base_interval:{self.base_interval}',
            f'    time_abs_min:{self.time_abs_min}',
            f'    time_abs_max:{self.time_abs_max}',
            f'    time_elapsed:{self.time_elapsed}',
            f'    image_size:{self.image_size}',
        ]
        
        lines.append('    all_events:')
        for event in self.all_events:
            lines.append(f'        {event}')
        
        return '\n'.join(lines)


def serialize(input_path, output_path, base_interval):
    
    record_data = RecordData(input_path, base_interval)
    
    if not os.path.exists(output_path):
        os.mkdir(output_path)
    
    metadata = []
    
    dummy_image = PIL.Image.new('RGB', record_data.image_size)
    
    status = {
        'cursor': None,
        'xy': None,
    }

    def on_control_events(status, interval):
        for ev in interval.control_events:
            if ev.name == 'start':
                if hasattr(ev, 'cursor'):
                    status['cursor'] = ev.cursor
            elif ev.name == 'stop':
                pass
    
    for i, interval in enumerate(record_data.intervals):
        
        # make image with the last status
        if interval.image is not None:
            screen = interval.image.screen
            if status['cursor'] and status['xy']:
                screen = status['cursor'].draw(screen, status['xy']) 
            input_image = screen
        else:
            input_image = dummy_image
        input_image.save(os.path.join(output_path, f'{i}.jpeg'))
        
        # output based on the image currently shown in image_view
        key_data = None
        if interval.key_event:
            ev = interval.key_event
            key_data = {'physical_key':ev.physical_key, 'event': 'down' if ev.key_mask else 'up'}
        
        button_data = None
        if interval.button_event:
            ev = interval.button_event
            button_data = {'button_id':ev.button_id, 'event':ev.event_type}
        
        control_data = None
        if interval.control_events:
            control_data = [str(ev) for ev in interval.control_events or []]
        
        metadata.append({
            'idx': i,
            'ge': interval.ge,
            'lt': interval.lt,
            'xy': interval.xy,
            'key': key_data,
            'button': button_data,
            'control': control_data,
        })
        
        if interval.control_events:
            on_control_events(status, interval)
    
        if interval.cursor_event:
            status['cursor'] = interval.cursor_event.cursor
    
        status['xy'] = interval.xy
    
    metadat_path = os.path.join(output_path, 'meta.json')
    json.dump(metadata, open(metadat_path, 'w'))


if __name__ == '__main__':
    
    import sys
    base_dir = sys.argv[1]
    serialize(base_dir, None, base_interval=0.1)

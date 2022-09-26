#! coding: utf-8
# Natural Language Processing Benchmark with GUI
# server.py
# Taichi iki
# 2022-09


import asyncio
import os
import json

import tornado.web
import tornado.template

from dataset_utils import available_datasets


PORT = 8889
TEMPLATES_DIR_PATH = 'templates'


class PageHandler(tornado.web.RequestHandler):

    def get(self, path):
        
        path_elem = path.split('/')
        
        if len(path_elem) == 3:
            self.get_page(*path_elem)
        elif len(path_elem) == 2:
            self.get_id(*path_elem)
        elif len(path_elem) == 1 and len(path_elem[0]):
            self.get_split(*path_elem)
        else:
            self.get_dataset()
        
    def get_dataset(self):
        
        kwargs = {
           'dataset_names': self.application.dataset_names,
        }
        
        file_path = os.path.join(TEMPLATES_DIR_PATH, 'dataset.html')
        t = tornado.template.Template(''.join(open(file_path).readlines()))
        data = t.generate(**kwargs)
        self.write(data)

    def get_split(self, dataset):
        
        kwargs = {
            'dataset': dataset,
            'split_names': self.application.dataset_split_names[dataset],
        }
        
        file_path = os.path.join(TEMPLATES_DIR_PATH, 'split.html')
        t = tornado.template.Template(''.join(open(file_path).readlines()))
        data = t.generate(**kwargs)
        self.write(data)

    def get_id(self, dataset, split):
        
        kwargs = {
            'dataset':dataset, 
            'split':split, 
            'num_examples':len(available_datasets[dataset].data[split])
        }
        
        file_path = os.path.join(TEMPLATES_DIR_PATH, 'id.html')
        t = tornado.template.Template(''.join(open(file_path).readlines()))
        data = t.generate(**kwargs)
        self.write(data)

    def get_page(self, dataset, split, _id):
        
        _id = int(_id) # needed to access by row
        metadata = available_datasets[dataset]
        data = metadata.data[split][_id]
        
        kwargs = {
            'dataset':dataset, 
            'split':split, 
            '_id':_id,
            'instruction': metadata.instruction,
            'labels': json.dumps(metadata.get_labels(data)),
            'contents': metadata.get_contents(data),
        }
       
        file_path = os.path.join(TEMPLATES_DIR_PATH, 'page.html')
        t = tornado.template.Template(''.join(open(file_path).readlines()))
        data = t.generate(**kwargs)
        self.write(data)


class TaskHandler(tornado.web.RequestHandler):

    def get(self, dataset, split, _id):
        
        init_mode = self.get_argument('init', '_id')
        
        _id = int(_id) # needed to access by row
        metadata = available_datasets[dataset]
        data = metadata.data[split][_id]
        
        if init_mode == '_id':
            init_url = f'/page/{dataset}/{split}/{_id}'
        elif init_mode == 'split':
            init_url = f'/page/{dataset}/{split}'
        elif init_mode == 'dataset':
            init_url = f'/page/{dataset}'
        else:
            init_url = f'/page/'
        
        kwargs = {
            'dataset':dataset, 
            'split':split, 
            '_id':_id,
            'init_url': init_url,
            'labels': json.dumps(metadata.get_labels(data)),
            'reward_mode': metadata.reward_mode,
        }
        
        file_path = os.path.join(TEMPLATES_DIR_PATH, 'task.html')
        t = tornado.template.Template(''.join(open(file_path).readlines()))
        data = t.generate(**kwargs)
        self.write(data)


class Application(tornado.web.Application):
    
    def __init__(self):
        
        self.dataset_names = available_datasets.names
        self.dataset_split_names = {k:v.split_names for k, v in available_datasets.items()}
        
        handlers = [
            (r"/task/(.*)/(.*)/(.*)", TaskHandler),
            (r"/page/(.*)", PageHandler),
        ]
        settings = dict(
            debug=True,
        )
        super().__init__(handlers, **settings)


async def main():
    
    print('load datasets')
    available_datasets.load_all()
    app = Application()
    print(f'start to listen to {PORT}')
    app.listen(PORT)
    stop_event = asyncio.Event()
    await stop_event.wait()


if __name__ == '__main__':

    asyncio.run(main())


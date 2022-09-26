# coding: utf-8


import datasets


REWARD_MODE_MATCH = 'match'
REWARD_MODE_DISTANCE = 'distance'


class DatasetAbstract(object):
    
    datasets_path = None
    reward_mode = REWARD_MODE_MATCH
    instruction = ''
    
    @classmethod
    def get_labels(cls, data):
        
        return []
    
    @classmethod
    def get_contents(cls, data):
        
        return []
    
    def __init__(self):
        
        self.data = None
        
    def load(self):
        
        self.data = datasets.load_dataset(*self.datasets_path)
        self.split_names = sorted(self.data.keys())


class DatasetMNLI(DatasetAbstract):

    datasets_path = ('glue', 'mnli')
    label_surfaces = ['entailment', 'neutral', 'contradiction']
    reward_mode = REWARD_MODE_MATCH
    instruction = """
What is the relationship of the hypothesis to the premise? 
Please answer from the following options: entailment, neutral, or contradiction.
""".strip()
    
    @classmethod
    def get_labels(cls, data):
        
        return [cls.label_surfaces[data['label']]]
    
    @classmethod
    def get_contents(cls, data):
        
        return [
            ('Premise', data['premise']),
            ('Hypothesis', data['hypothesis'])
        ]


class DatasetSTSB(DatasetAbstract):
    
    datasets_path = ('glue', 'stsb')
    reward_mode = REWARD_MODE_DISTANCE
    instruction = """
Predict the similarity between sentence1 and sentence2.
Answer with a number between 0 and 5, considering 5 when the sentences have exactly the same meaning.
""".strip()
    
    @classmethod
    def get_labels(cls, data):
        
        return [data['label']]
    
    @classmethod
    def get_contents(cls, data):
        
        return [
            ('Sentence1', data['sentence1']),
            ('Sentence2', data['sentence2'])
        ]


class DatasetSQuAD(DatasetAbstract):
    
    datasets_path = ('squad',)
    reward_mode = REWARD_MODE_MATCH
    instruction = """
Read the content and answer the following question.
If you cannot answer based on the content, please submit unanswerable.
""".strip()
    
    @classmethod
    def get_labels(cls, data):
        
        return data['answers']['text']

    @classmethod
    def get_contents(cls, data):
        
        return [
            ('Context', data['context']),
            ('Question', data['question'])
        ]


class DatasetsBinder(object):
    
    def __init__(self, mapping):
        
        self.mapping = mapping
        
    def __getitem__(self, key):
        
        return self.mapping[key]
    
    def items(self):
        
        return self.mapping.items()
    
    def load_all(self):
    
        for k, v in self.mapping.items():
            v.load()
    
    @property
    def names(self):
        
        return sorted(self.mapping.keys())
    
    
available_datasets = DatasetsBinder({
    'MNLI': DatasetMNLI(),
    'STSB': DatasetSTSB(),
    'SQuAD': DatasetSQuAD()
})


if __name__ == '__main__':
    
    # To make a cache files
    available_datasets.load_all()

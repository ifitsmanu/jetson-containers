#!/usr/bin/env python3
from local_llm import Plugin, LocalLM, ChatHistory
from local_llm.utils import print_table


class ChatQuery(Plugin):
    """
    Plugin that feeds incoming text or ChatHistory to LLM and generates the reply.
    It can either internally manage the ChatHistory, or that can be done externally.
    """
    def __init__(self, model, **kwargs):
        """
        Parameters:
        
          model (str|LocalLM) -- model name/path or loaded LocalLM model instance
          
        kwargs (these get passed to LocalLM.from_pretrained() if model needs loaded)
        
          api (str) -- the model backend API to use:  'auto_gptq', 'awq', 'mlc', or 'hf'
                       if left as None, it will attempt to be automatically determined.
          quant (str) -- for AWQ or MLC, either specify the quantization method,
                         or the path to the quantized model (AWQ and MLC API's only)
          vision_model (str) -- for VLMs, override the vision embedding model (CLIP)
                                otherwise, it will use the CLIP variant from the config.
                                
        kwargs (these get passed to ChatHistory initializer)
        
          chat_template (str|dict) -- either a chat template dict, or the name of the 
                                       chat template to use like 'llama-2', 'vicuna-v1'
                                       If None, will attempt to determine model type.        
          system_prompt (str) -- set the default system prompt
                                 if None, will use system prompt from the template.
                                 
        kwargs (generation parameters)

          max_new_tokens (int) -- the number of tokens to output in addition to the prompt (default: 128)
          min_new_tokens (int) -- force the model to generate a set number of output tokens (default: -1)
          do_sample (bool) -- if True, temperature/top_p will be used.  Otherwise, greedy search (default: False)
          repetition_penalty -- the parameter for repetition penalty. 1.0 means no penalty (default: 1.0)  
          temperature (float) -- randomness token sampling parameter (default=0.7, only used if do_sample=True)
          top_p (float) -- if set to float < 1 and do_sample=True, only the smallest set of most probable tokens
                           with probabilities that add up to top_p or higher are kept for generation (default 0.95)          
        """
        super().__init__(**kwargs)

        if isinstance(model, str):
            self.model = LocalLM.from_pretrained(model, **kwargs)
        else:
            self.model = model
            
        self.chat_history = ChatHistory(self.model, **kwargs)
        
        self.max_new_tokens = kwargs.get('max_new_tokens', 128)
        self.min_new_tokens = kwargs.get('min_new_tokens', -1)
        
        self.do_sample = kwargs.get('do_sample', False)
        self.repetition_penalty = kwargs.get('repetition_penalty', 1.0)
        self.temperature = kwargs.get('temperature', 0.7)
        self.top_p = kwargs.get('top_p', 0.95)
            
    def process(self, input, **kwargs):
        """
        Generate the reply to a prompt or the latest ChatHistory.
        
        Parameters:
        
          input (str|dict|ChatHistory) -- either a string prompt from the user,
                                          a ChatEntry dict, or ChatHistory dict.
                                          
        Returns:
        
          The generated text (token by token), if input was a string or dict.
          If input was a ChatHistory, returns the streaming iterator/generator.
        """
        if isinstance(input, str) or isinstance(input, dict):
            self.chat_history.append(role='user', msg=input)
            chat_history = self.chat_history
        elif isinstance(input, ChatHistory):
            chat_history = input
        else:
            raise TypeError(f"LLMQuery plugin expects inputs of type str, dict, or ChatHistory (was {type(input)})")

        embedding, position = chat_history.embed_chat()
        
        output = self.model.generate(
            embedding, 
            streaming=True, 
            kv_cache=chat_history.kv_cache,
            max_new_tokens=self.max_new_tokens,
            min_new_tokens=self.min_new_tokens,
            do_sample=self.do_sample,
            repetition_penalty=self.repetition_penalty,
            temperature=self.temperature,
            top_p=self.top_p,
            **kwargs
        )
        
        if not isinstance(input, ChatHistory):
            bot_reply = self.chat_history.append(role='bot', text='')
            
            for token in output:
                bot_reply.text += token
                self.output(token)
                
            bot_reply.text = output.output_text
            self.chat_history.kv_cache = output.kv_cache
            
            #print_table(self.model.stats)
        else:
            return output
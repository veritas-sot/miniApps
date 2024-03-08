from loguru import logger

# veritas
from veritas.plugin import jobschleuder

@jobschleuder("hello_world")
def hello_world(*args, **kwargs):
    print(f'hello world {args} {kwargs}')

# confparse

A small parser for config files with one `key = value` per line. A `#` starts a comment.

```python
from confparse import parse

parse("name = api\nport = 8080\ndebug = yes\n")
# {'name': 'api', 'port': 8080, 'debug': True}
```

The schema in `confparse.SCHEMA` gives each known key its type. A key the schema does not name is
kept as text. A value of the wrong type raises `ConfigError`, which names the line.

Run the tests with `python3 -m unittest discover -s tests`.

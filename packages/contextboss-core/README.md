# contextboss-core

The core engine of [ContextBoss](../..): persistent context storage, dynamic token
budgeting, priority-based assembly, compression and reliable deletion.

```bash
pip install -e ".[dev]"
pytest
```

Import path is still `contextboss`:

```python
from contextboss import ContextManager, ContextAssembler
```

See the [repository README](../../README.md) for the full picture.

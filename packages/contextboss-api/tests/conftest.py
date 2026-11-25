import os
import sys

_HERE = os.path.dirname(__file__)
for p in (
    os.path.join(_HERE, "..", "src"),
    os.path.join(_HERE, "..", "..", "contextboss-core", "src"),
):
    sys.path.insert(0, os.path.abspath(p))

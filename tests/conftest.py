import importlib.util
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "app"))
spec = importlib.util.spec_from_file_location("killswitch_main", root / "killswitch" / "main.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["killswitch_main"] = mod
spec.loader.exec_module(mod)

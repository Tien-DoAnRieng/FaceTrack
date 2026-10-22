"""Compatibility entry point. Start the complete project with python run.py."""
if __name__ == '__main__':
    import runpy
    from pathlib import Path
    runpy.run_path(str(Path(__file__).with_name('run.py')), run_name='__main__')
else:
    import sys
    from frontend import gradio_app
    sys.modules[__name__] = gradio_app

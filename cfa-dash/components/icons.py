from dash_iconify import DashIconify


def icon(name: str, size: int = 16, **kwargs):
    return DashIconify(icon=name, width=size, height=size, **kwargs)

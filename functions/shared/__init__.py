"""Azure-binding-free logic for the HR data pipeline.

Everything here is plain Python, unit-testable without the Azure Functions
runtime. The HTTP wrappers in ``function_app.py`` only parse requests and
delegate into this package.
"""

import nox

# Stelle sicher, dass uv als Backend verwendet wird
nox.options.default_venv_backend = "uv"


@nox.session(python=["3.10", "3.11", "3.12", "3.13"])
def tests(session):
    session.install(".[test]")
    session.run("pytest")
    # session.run("coverage", "run", "-m", "pytest")
    # session.run("coverage", "report", "-m")

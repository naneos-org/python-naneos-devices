# import pytest

# from naneos.partector2.hello import hello_world

# def test_hello_world():
#     assert hello_world() == "Hello World!"

# from naneos.partector2.skeleton import fib, main

# __author__ = "huegi"
# __copyright__ = "huegi"
# __license__ = "MIT"


# def test_fib():
#     """API Tests"""
#     assert fib(1) == 1
#     assert fib(2) == 1
#     assert fib(7) == 13
#     with pytest.raises(AssertionError):
#         fib(-10)


# def test_main(capsys):
#     """CLI Tests"""
#     # capsys is a pytest fixture that allows asserts agains stdout/stderr
#     # https://docs.pytest.org/en/stable/capture.html
#     main(["7"])
#     captured = capsys.readouterr()
#     assert "The 7-th Fibonacci number is 13" in captured.out

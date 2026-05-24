import os


for file in os.listdir("./tests"):
    if file.endswith(".py") and file != "run_tests.py":
        try:
            print("TEST", file)
            __import__(file.removesuffix(".py"))
        except Exception as e:
            print(e)

import os
import time

def start_in_terminal(name, command):
    os.system(f'powershell.exe -Command "Start-Process powershell -ArgumentList \'-NoExit\', \'-Command\', \'{command}\'"')

if __name__ == "__main__":
    start_in_terminal("Action Server", "rasa run actions")

    time.sleep(30)

    start_in_terminal("Rasa Shell", "rasa shell")

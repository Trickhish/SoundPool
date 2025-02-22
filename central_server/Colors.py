import re


NONE = '\033[0m'
BLACK = '\033[30m'
RED = '\033[31m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
BLUE = '\033[34m'
MAGENTA = '\033[35m'
CYAN = '\033[36m'
WHITE = '\033[37m'
LIGHT_BLACK = '\033[90m'
LIGHT_RED = '\033[91m'
LIGHT_GREEN = '\033[92m'
LIGHT_YELLOW = '\033[93m'
LIGHT_BLUE = '\033[94m'
LIGHT_MAGENTA = '\033[95m'
LIGHT_CYAN = '\033[96m'
LIGHT_WHITE = '\033[97m'

BOLD = '\033[1m'
UNDERLINE = '\033[4m'

colorList = [BOLD, UNDERLINE, NONE, BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, LIGHT_BLACK, LIGHT_RED, LIGHT_GREEN, LIGHT_BLUE, LIGHT_MAGENTA, LIGHT_WHITE, LIGHT_YELLOW, LIGHT_CYAN]

def lastUsed(s):
    color_pattern = re.compile(r"\x1b\[[0-9;]*m")
    color_codes = color_pattern.findall(s)
    
    if color_codes:
        return(color_codes[-1])
    else:
        return(None)

    mxc=NONE
    mxp=-1
    for cl in colorList:
        pp = s.rfind(cl)
        print(f"{cl}DDD ({pp}){NONE}")
        if pp>mxp:
            mxp=pp
            mxc=cl
    
    print(f"{mxc}FOUND THAT COLOR{NONE}")
    return(mxc)
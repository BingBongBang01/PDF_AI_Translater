import cProfile
import pstats
import io
import sys
from pathlib import Path

def profile_function(func):
    """Decorator to profile a single function"""
    def wrapper(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()
        result = func(*args, **kwargs)
        pr.disable()
        
        s = io.StringIO()
        sortby = 'cumulative'
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        ps.print_stats(30) # Print top 30
        
        Path("profile_results.txt").write_text(s.getvalue())
        print("Profile saved to profile_results.txt")
        return result
    return wrapper

if __name__ == "__main__":
    print("Run this script by importing profile_function and wrapping your target methods.")

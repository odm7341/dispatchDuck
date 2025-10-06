#!/usr/bin/env python3

"""
Dispatchwrapparr - Simple tsp wrapper for Dispatcharr

Usage: dispatchwrapparr.py -i <URL> -ua <User Agent String>
Optional: -proxy <proxy server>
"""

import os
import sys
import argparse
import subprocess
import signal

__version__ = "2.0.0"

def parse_args():
    parser = argparse.ArgumentParser(description="Dispatchwrapparr: Simple tsp wrapper for Dispatcharr")
    parser.add_argument("-i", required=True, help="Required: Stream URL")
    parser.add_argument("-ua", required=True, help="Required: User-Agent string")
    parser.add_argument("-proxy", help="Optional: HTTP proxy server (e.g. http://127.0.0.1:8888)")
    parser.add_argument("-v", "--version", action="version", version=f"Dispatchwrapparr {__version__}")
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Set proxy environment variable if provided
    if args.proxy:
        os.environ["HTTP_PROXY"] = args.proxy
        os.environ["HTTPS_PROXY"] = args.proxy
    
    # Set user agent for tsp
    user_agent = args.ua
    
    # Construct tsp command
    cmd = [
        "tsp",
        "--user-agent", user_agent,
        "-I", "http",
        "-P", "continuity",
        "-O", "fifo"
    ]
    
    # Add the stream URL
    cmd.extend([args.i])
    
    print(f"Running tsp command: {' '.join(cmd)}", file=sys.stderr)
    
    try:
        # Run tsp and pipe output to stdout
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=sys.stderr)
        
        # Read output in chunks and write to stdout
        while True:
            data = process.stdout.read(188 * 64)  # Match buffer settings of Dispatcharr
            if not data:
                break
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
            
    except KeyboardInterrupt:
        print("Stream interrupted, canceling.", file=sys.stderr)
        process.terminate()
        process.wait()
    except Exception as e:
        print(f"Error running tsp: {e}", file=sys.stderr)
        sys.exit(1)

# Set default SIGPIPE behavior so dispatchwrapparr exits cleanly when the pipe is closed
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

if __name__ == "__main__":
    main()

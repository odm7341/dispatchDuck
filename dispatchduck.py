#!/usr/bin/env python3

"""
DispatchDuck - Simple tsp wrapper for Dispatcharr

Usage: dispatchduck.py -i <URL> -ua <User Agent String>
Optional: -d, --debug
"""

import sys
import argparse
import subprocess
import signal

__version__ = "2.0.0"

def parse_args():
    parser = argparse.ArgumentParser(description="Dispatchduck: Simple tsp wrapper for Dispatcharr")
    parser.add_argument("-i", required=True, help="Required: Stream URL")
    parser.add_argument("-ua", required=True, help="Required: User-Agent string")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug output")
    parser.add_argument("-v", "--version", action="version", version=f"Dispatchduck {__version__}")
    return parser.parse_args()

def main():
    args = parse_args()

    if args.debug:
        print(f"[DEBUG] Stream URL: {args.i}", file=sys.stderr)
        print(f"[DEBUG] User Agent: {args.ua}", file=sys.stderr)

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

    if args.debug:
        print(f"[DEBUG] Running tsp command: {' '.join(cmd)}", file=sys.stderr)
    else:
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
        if args.debug:
            print("[DEBUG] Stream interrupted by user, canceling.", file=sys.stderr)
        else:
            print("Stream interrupted, canceling.", file=sys.stderr)
        process.terminate()
        process.wait()
    except Exception as e:
        if args.debug:
            print(f"[DEBUG] Error running tsp: {e}", file=sys.stderr)
            print(f"[DEBUG] Command that failed: {' '.join(cmd)}", file=sys.stderr)
        else:
            print(f"Error running tsp: {e}", file=sys.stderr)
        sys.exit(1)

# Set default SIGPIPE behavior so dispatchduck exits cleanly when the pipe is closed
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

if __name__ == "__main__":
    main()

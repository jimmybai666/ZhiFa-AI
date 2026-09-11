"""
Launch ZhiFa-Eval server.

Usage:
    python run.py
"""
import uvicorn

if __name__ == "__main__":
    print("\n  ZhiFa-Eval → http://localhost:8080\n")
    uvicorn.run("zhifa_eval.server:app", host="0.0.0.0", port=8080, reload=True)

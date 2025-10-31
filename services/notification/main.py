"""
Notification Service - Placeholder until full implementation
"""
from fastapi import FastAPI

app = FastAPI(title="Notification Service", version="1.0.0")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "notification"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
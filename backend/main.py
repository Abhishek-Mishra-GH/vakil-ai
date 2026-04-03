from fastapi import FastAPI, Request

app = FastAPI()

@app.get("/")
async def read_root():
    return {"Hello": "World"}
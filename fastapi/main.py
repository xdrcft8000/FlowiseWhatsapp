from fastapi import FastAPI

app = FastAPI()

@app.get("/api/hello")
def read_root():
    return {"Hello": "World"}
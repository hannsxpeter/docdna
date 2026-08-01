from flask import Flask

app = Flask(__name__)


@app.get("/orders")
def list_orders():
    return {"orders": []}


@app.post("/orders")
def create_order():
    return {"id": "ord_1"}, 201


@app.get("/orders/<order_id>")
def get_order(order_id):
    return {"id": order_id}


@app.post("/orders/<order_id>/refunds")
def refund_order(order_id):
    return {"id": order_id, "refunded": True}


if __name__ == "__main__":
    app.run(port=8000)

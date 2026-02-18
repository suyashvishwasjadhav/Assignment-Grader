from app import app
from diagram_routes import register_diagram_routes

# Register diagram evaluation routes
register_diagram_routes(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
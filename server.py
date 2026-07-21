from app import config, create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.port(), debug=True)

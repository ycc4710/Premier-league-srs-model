from flask import Flask, request, jsonify
import subprocess
import os

app = Flask(__name__)

@app.route('/run_simulation')
def run_simulation():
    std_error = request.args.get('std_error', '7')
    num_sim = request.args.get('num_sim', '1000')
    cmd = [
        'python3', os.path.join(os.path.dirname(__file__), 'simulate_season.py'),
        '--std_error', str(std_error),
        '--num_sim', str(num_sim)
    ]
    subprocess.run(cmd, check=True)
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(port=5000)

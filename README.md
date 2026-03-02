# Premier-league-srs-model
Editted on the basis of lcbeas (https://github.com/lcbeas/nba_srs_ratings) 

How to use:
- For Windows - 
1. `git clone {website}` in cmd (please pip install `git` beforehand if you haven't installed it)
2. open the downloaded folder in your ide (vscode, pycharm, etc.)
3. run `pip install -q -r requirements.txt` in terminal
4. run `python -m scripts.generate_site_data` in terminal (if you do not have an API key, please go to https://www.football-data.org and register)
5. run `python -m http.server 8000 --directory site` in terminal
6. go to http://localhost:8000 if it does not pop out automatically
7. NOW YOU SEE IT! ^^

- For Mac -
  
Follow Professor Beasly's README because i know nothing about mac (ORZ

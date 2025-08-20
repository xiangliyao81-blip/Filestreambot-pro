services:
  - type: web
    name: telegram-bot
    env: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: python app.py
    envVars:
      - key: BOT_TOKEN
        sync: false
      - key: OPENAI_API_KEY
        sync: false
      - key: SERPAPI_KEY
        sync: false
      - key: PORT
        value: 10000

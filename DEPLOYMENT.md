# Deployment Guide

This guide covers various deployment options for the Twitter Auto-Translation Bot, from local development to production cloud deployments.

## =� Quick Deployment Options

### Option 1: GitHub Actions (Recommended - Free)
**Best for:** Personal use, automated scheduling, zero maintenance
**Cost:** Free (GitHub provides generous limits)

### Option 2: Local Machine
**Best for:** Development, testing, full control
**Cost:** Free (uses your machine)

### Option 3: Cloud Platforms
**Best for:** Always-on, scalable, professional use
**Cost:** $0-15/month depending on platform

---

## =� Pre-Deployment Checklist

Before deploying, ensure you have:

- [x] Twitter Developer Account with API keys
- [x] Google Gemini API key
- [x] Multiple Twitter accounts (primary + language accounts)
- [x] All API credentials ready
- [x] Target languages configured
- [x] Tested locally with `python main.py test`

---

## =' Option 1: GitHub Actions Deployment

### Why GitHub Actions?
- **Free:** 2,000 minutes/month for private repos, unlimited for public
- **Automated:** Runs every 30 minutes automatically
- **Zero Maintenance:** No servers to manage
- **Perfect for Personal Use:** Handles rate limits gracefully

### Setup Steps

#### 1. Repository Setup
```bash
# Fork or create new repository
git clone <your-repo-url>
cd twitter_bot

# Push to GitHub if not already there
git add .
git commit -m "Initial commit"
git push origin main
```

#### 2. Configure GitHub Secrets
Go to your repository on GitHub:
1. Click **Settings** � **Secrets and variables** � **Actions**
2. Click **New repository secret**
3. Add these secrets one by one:

**Primary Account Secrets:**
```
PRIMARY_TWITTER_CONSUMER_KEY=your_actual_key
PRIMARY_TWITTER_CONSUMER_SECRET=your_actual_secret
PRIMARY_TWITTER_ACCESS_TOKEN=your_actual_token
PRIMARY_TWITTER_ACCESS_TOKEN_SECRET=your_actual_token_secret
PRIMARY_TWITTER_USERNAME=your_username
```

**Language Account Secrets (repeat for each language):**
```
JA_TWITTER_CONSUMER_KEY=japanese_key
JA_TWITTER_CONSUMER_SECRET=japanese_secret
JA_TWITTER_ACCESS_TOKEN=japanese_token
JA_TWITTER_ACCESS_TOKEN_SECRET=japanese_token_secret

DE_TWITTER_CONSUMER_KEY=german_key
DE_TWITTER_CONSUMER_SECRET=german_secret
DE_TWITTER_ACCESS_TOKEN=german_token
DE_TWITTER_ACCESS_TOKEN_SECRET=german_token_secret
```

**Google API Secret:**
```
GOOGLE_API_KEY=your_gemini_api_key
```

#### 3. Create GitHub Workflow
Create `.github/workflows/twitter-bot.yml`:

```yaml
name: Twitter Translation Bot

on:
  schedule:
    - cron: '*/30 * * * *'  # Run every 30 minutes
  workflow_dispatch:  # Allow manual runs

jobs:
  translate-tweets:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Create directories
      run: |
        mkdir -p logs drafts/pending drafts/posted
    
    - name: Run bot
      env:
        # Primary account
        PRIMARY_TWITTER_CONSUMER_KEY: ${{ secrets.PRIMARY_TWITTER_CONSUMER_KEY }}
        PRIMARY_TWITTER_CONSUMER_SECRET: ${{ secrets.PRIMARY_TWITTER_CONSUMER_SECRET }}
        PRIMARY_TWITTER_ACCESS_TOKEN: ${{ secrets.PRIMARY_TWITTER_ACCESS_TOKEN }}
        PRIMARY_TWITTER_ACCESS_TOKEN_SECRET: ${{ secrets.PRIMARY_TWITTER_ACCESS_TOKEN_SECRET }}
        PRIMARY_TWITTER_USERNAME: ${{ secrets.PRIMARY_TWITTER_USERNAME }}
        
        # Language accounts (add more as needed)
        JA_TWITTER_CONSUMER_KEY: ${{ secrets.JA_TWITTER_CONSUMER_KEY }}
        JA_TWITTER_CONSUMER_SECRET: ${{ secrets.JA_TWITTER_CONSUMER_SECRET }}
        JA_TWITTER_ACCESS_TOKEN: ${{ secrets.JA_TWITTER_ACCESS_TOKEN }}
        JA_TWITTER_ACCESS_TOKEN_SECRET: ${{ secrets.JA_TWITTER_ACCESS_TOKEN_SECRET }}
        
        DE_TWITTER_CONSUMER_KEY: ${{ secrets.DE_TWITTER_CONSUMER_KEY }}
        DE_TWITTER_CONSUMER_SECRET: ${{ secrets.DE_TWITTER_CONSUMER_SECRET }}
        DE_TWITTER_ACCESS_TOKEN: ${{ secrets.DE_TWITTER_ACCESS_TOKEN }}
        DE_TWITTER_ACCESS_TOKEN_SECRET: ${{ secrets.DE_TWITTER_ACCESS_TOKEN_SECRET }}
        
        # Google API
        GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
        GEMINI_MODEL: gemini-2.5-flash-lite
        
        # App settings
        POLL_INTERVAL_SECONDS: 300
        LOG_LEVEL: INFO
      run: |
        python main.py once
    
    - name: Upload logs
      uses: actions/upload-artifact@v3
      if: always()
      with:
        name: bot-logs
        path: logs/
        retention-days: 7
    
    - name: Upload drafts
      uses: actions/upload-artifact@v3
      if: always()
      with:
        name: pending-drafts
        path: drafts/
        retention-days: 30
```

#### 4. Test & Monitor
1. Go to **Actions** tab in your repository
2. Click **Run workflow** to test manually
3. Check logs for any errors
4. Monitor automated runs every 30 minutes

### GitHub Actions Monitoring

**View Logs:**
1. Go to Actions tab
2. Click on a workflow run
3. Expand "Run bot" step to see detailed logs

**Download Artifacts:**
- Logs and drafts are automatically saved as artifacts
- Download from the workflow run page
- Useful for debugging and monitoring

---

## =� Option 2: Local Machine Deployment

### Development Setup
```bash
# Clone and setup
git clone <your-repo>
cd twitter_bot
./setup.sh  # or manual setup

# Copy and configure environment
cp config/.env.template .env
nano .env  # Add your API keys

# Test setup
python test_components.py
python main.py test
```

### Running Locally

**Interactive Mode:**
```bash
python run_local.py
```

**One-time Run:**
```bash
python main.py once
```

**Continuous Mode:**
```bash
python main.py
```

### Production Local Setup (Linux/Mac)

**Using systemd (Linux):**
```bash
# Create service file
sudo tee /etc/systemd/system/twitter-bot.service > /dev/null <<EOF
[Unit]
Description=Twitter Translation Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/venv/bin
ExecStart=$(pwd)/venv/bin/python main.py
Restart=always
RestartSec=300
StandardOutput=append:$(pwd)/logs/systemd.log
StandardError=append:$(pwd)/logs/systemd.log

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl enable twitter-bot
sudo systemctl start twitter-bot

# Check status
sudo systemctl status twitter-bot
```

**Using cron (Mac/Linux):**
```bash
# Edit crontab
crontab -e

# Add this line to run every 30 minutes
*/30 * * * * cd /path/to/twitter_bot && ./venv/bin/python main.py once >> logs/cron.log 2>&1
```

---

##  Option 3: Cloud Platform Deployment

### Railway (Recommended Free Option)

**Why Railway?**
- $5/month free credits
- Easy GitHub integration
- Automatic deployments
- Built-in monitoring

**Setup:**
1. Connect GitHub repository at [railway.app](https://railway.app)
2. Add environment variables in Railway dashboard
3. Deploy automatically

**Railway Configuration:**
```bash
# Procfile (create in root directory)
web: python main.py
```

### Render

**Setup:**
1. Connect repository at [render.com](https://render.com)
2. Choose "Background Worker" service type
3. Add environment variables
4. Deploy

**Render Configuration:**
```yaml
# render.yaml
services:
  - type: worker
    name: twitter-bot
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python main.py
    envVars:
      - key: PRIMARY_TWITTER_CONSUMER_KEY
        sync: false
      # Add all other environment variables
```

### Oracle Cloud (Always Free)

**Why Oracle Cloud?**
- Always free ARM instances (24GB RAM, 4 CPU cores)
- No time limits
- Perfect for personal projects

**Setup:**
1. Create Oracle Cloud account
2. Launch ARM instance (Ubuntu)
3. Install Python and dependencies
4. Deploy code and run with systemd

**Oracle Setup Commands:**
```bash
# On Oracle instance
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git

# Clone repository
git clone <your-repo>
cd twitter_bot

# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp config/.env.template .env
nano .env  # Add your API keys

# Test
python test_components.py
python main.py test

# Setup systemd service (use systemd config from above)
```

### Heroku (Paid)

**Setup:**
```bash
# Install Heroku CLI and login
heroku create your-bot-name

# Add environment variables
heroku config:set PRIMARY_TWITTER_CONSUMER_KEY=your_key
# ... add all other variables

# Deploy
git push heroku main

# Scale worker
heroku ps:scale worker=1
```

**Procfile:**
```
worker: python main.py
```

---

## =� Cost Comparison

| Platform | Free Tier | Paid Tier | Best For |
|----------|-----------|-----------|----------|
| GitHub Actions | 2,000 min/month | $0.008/min | Personal, automated |
| Railway | $5 credits/month | $0.000463/GB-hour | Small projects |
| Render | 750 hours/month | $7/month | Background services |
| Oracle Cloud | Always free ARM | Paid tiers available | Always-on, powerful |
| Heroku | No free tier | $7/month | Easy deployment |
| Local Machine | Free | Electricity costs | Development, testing |

---

## = Security Best Practices

### API Key Management
1. **Never commit API keys** to version control
2. **Use different keys** for development/production
3. **Rotate keys regularly** (monthly recommended)
4. **Monitor API usage** for unusual activity

### Platform Security
1. **Enable 2FA** on all accounts (GitHub, Twitter, Google)
2. **Use least privilege** - minimum required permissions
3. **Monitor deployments** - check logs regularly
4. **Keep dependencies updated** - security patches

### Backup & Recovery
```bash
# Backup important files
tar -czf twitter-bot-backup.tar.gz logs/ drafts/ config/languages.json

# Schedule regular backups
echo "0 2 * * * cd /path/to/twitter_bot && tar -czf backups/backup-\$(date +\%Y\%m\%d).tar.gz logs/ drafts/" | crontab -
```

---

## =� Monitoring & Maintenance

### Log Monitoring
```bash
# Real-time log monitoring
tail -f logs/twitter_bot_$(date +%Y-%m-%d).log

# Check for errors
grep -i error logs/twitter_bot_*.log

# Monitor API usage
python main.py status
```

### Health Checks
```bash
# Test connections
python main.py test

# Check component functionality
python test_components.py

# View pending drafts
python main.py drafts
```

### Performance Monitoring

**Key Metrics to Track:**
- Translation success rate
- API usage vs limits
- Draft accumulation
- Error frequency
- Response times

**GitHub Actions Monitoring:**
- Check workflow success rate
- Monitor artifact sizes
- Review failure patterns

**Cloud Platform Monitoring:**
- Resource usage (CPU, memory)
- Network activity
- Error logs
- Uptime statistics

---

## =� Troubleshooting Common Issues

### GitHub Actions Issues

**Problem:** Workflow doesn't trigger
```yaml
# Check cron syntax and timezone
on:
  schedule:
    - cron: '*/30 * * * *'  # Every 30 minutes
  workflow_dispatch:  # Always include for manual runs
```

**Problem:** Secrets not working
- Verify exact secret names match workflow file
- Check for typos in secret values
- Ensure secrets are set at repository level, not organization

**Problem:** Job fails with import errors
```yaml
# Ensure all dependencies are installed
- name: Install dependencies
  run: |
    pip install -r requirements.txt
    pip install --upgrade pip
```

### Cloud Platform Issues

**Problem:** App crashes on startup
1. Check environment variables are set correctly
2. Verify Python version compatibility
3. Check logs for import errors
4. Ensure all directories exist

**Problem:** Rate limits exceeded
- Monitor API usage with `python main.py status`
- Adjust `POLL_INTERVAL_SECONDS` to reduce frequency
- Check for duplicate deployments running

**Problem:** Memory issues
- Use lighter Gemini model (`gemini-2.5-flash-lite`)
- Clear old logs and drafts regularly
- Monitor memory usage patterns

### General Issues

**Problem:** Translations not posting
1. Verify language account credentials
2. Check Twitter account permissions
3. Review character limits and content policies
4. Check for account suspensions

**Problem:** High API costs
1. Monitor Gemini API usage in Google Console
2. Set spending limits
3. Use more efficient models
4. Implement caching improvements

---

## = Scaling & Optimization

### For High-Volume Accounts
```python
# Increase polling frequency
POLL_INTERVAL_SECONDS=60  # Check every minute

# Use faster model for better quality
GEMINI_MODEL=gemini-1.5-pro

# Consider Twitter API paid tier for higher limits
```

### For Multiple Languages
1. **Gradual Rollout:** Add one language at a time
2. **Monitor Costs:** Track API usage per language
3. **Optimize Prompts:** Language-specific optimizations
4. **Parallel Processing:** Consider async processing for scale

### Performance Optimization
```python
# Implement caching
# Enable batch processing
# Use connection pooling
# Optimize prompt lengths
```

---

## =� Support & Maintenance

### Regular Maintenance Tasks

**Weekly:**
- Check error logs
- Monitor API usage
- Review draft accumulation
- Test key components

**Monthly:**
- Rotate API keys
- Update dependencies
- Clean old logs/drafts
- Review costs

**Quarterly:**
- Security audit
- Performance review
- Feature updates
- Backup verification

### Getting Help

1. **Check Logs First:** Most issues are logged with clear error messages
2. **Test Components:** Run `python test_components.py`
3. **Verify Configuration:** Double-check API keys and settings
4. **Check Platform Status:** Twitter API, Google AI, deployment platform

### Updating the Bot

```bash
# Update code
git pull origin main

# Update dependencies
pip install -r requirements.txt --upgrade

# Test before deploying
python test_components.py
python main.py test

# Deploy (depends on your platform)
git push  # For GitHub Actions/cloud platforms
sudo systemctl restart twitter-bot  # For local systemd
```

---

## <� Production Readiness Checklist

Before going live with your deployment:

- [ ] All API keys tested and working
- [ ] Multiple languages configured and tested
- [ ] Monitoring and alerting setup
- [ ] Backup strategy implemented
- [ ] Security best practices followed
- [ ] Rate limits and costs understood
- [ ] Error handling verified
- [ ] Documentation updated
- [ ] Team access configured (if applicable)
- [ ] Incident response plan ready

---

**Happy Deploying! =�**

Choose the deployment option that best fits your needs, budget, and technical requirements. GitHub Actions is perfect for personal use, while cloud platforms offer more control and scaling options for professional use.
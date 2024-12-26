from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
from pandas.tseries.offsets import BDay

templates = Jinja2Templates(directory="templates")
app = FastAPI()



@app.get("/", response_class=HTMLResponse)
async def form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})

from pandas.tseries.offsets import BDay

@app.post("/generate_report/")
async def generate_report(
    ticker: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    volume_threshold: float = Form(...),
    price_threshold: float = Form(...),
    holding_period: int = Form(...),
):
    # Download stock data from yahoo finance
    stock_data = yf.download(ticker, start=start_date, end=end_date)
    if stock_data.empty:
        return {"error": "No data found for the given ticker and date range."}

    # Sell dates could land on holidays or weekends
    # Ensure dates are aligned to business days
    stock_data = stock_data.asfreq('B')

    # 20-day average volume
    stock_data['20d_avg_volume'] = stock_data['Volume'].rolling(window=20).mean()

    # Identify breakout days
    stock_data['Volume_Breakout'] = stock_data['Volume'].squeeze() > volume_threshold / 100 * stock_data['20d_avg_volume']
    stock_data['Price_Change'] = (stock_data['Close'] / stock_data['Close'].shift(1) - 1) * 100
    stock_data['Price_Breakout'] = stock_data['Price_Change'] >= price_threshold
    stock_data['Breakout_Day'] = stock_data['Volume_Breakout'] & stock_data['Price_Breakout']

    # Filter breakout days
    breakout_days = stock_data[stock_data['Breakout_Day']]
    results = []

    
    for index, row in breakout_days.iterrows():
        buy_price = row['Close'].iloc[0]
        sell_date = index + timedelta(days=holding_period)

        # Check if sell_date exists in the stock data
        try:
            sell_price = stock_data.loc[sell_date, 'Close'].iloc[0]
            return_pct = (sell_price - buy_price) / buy_price * 100
            results.append({
                'Buy_Date': index.strftime('%Y-%m-%d'),
                'Buy_Price': buy_price,
                'Sell_Date': sell_date.strftime('%Y-%m-%d'),
                'Sell_Price': sell_price,
                'Return_Percentage': return_pct
            })
        except KeyError:
            # Find the nearest valid trading day if sell_date is missing
            nearest_sell_date = sell_date + BDay()  # Shift to next valid trading day
            if nearest_sell_date not in stock_data.index:
                nearest_sell_date = sell_date - BDay()  # Shift to previous valid trading day if needed

            nearest_sell_price = stock_data.loc[nearest_sell_date, 'Close'].iloc[0]
            return_pct = (nearest_sell_price - buy_price) / buy_price * 100
            results.append({
                'Buy_Date': index.strftime('%Y-%m-%d'),
                'Buy_Price': buy_price,
                'Sell_Date': nearest_sell_date.strftime('%Y-%m-%d'),
                'Sell_Price': nearest_sell_price,
                'Return_Percentage': return_pct
            })
            print(f"Sell date {sell_date.strftime('%Y-%m-%d')} not found, using {nearest_sell_date.strftime('%Y-%m-%d')} instead.")

    # Create a DataFrame with results
    results_df = pd.DataFrame(results)
    if results_df.empty:
        return {"error": "No breakout days found."}
    
    # Save results to CSV
    csv_file = f"{ticker}_breakout_report.csv"
    results_df.to_csv(csv_file, index=False)

    # Provide downloadable link
    return FileResponse(csv_file, media_type='text/csv', filename=csv_file)
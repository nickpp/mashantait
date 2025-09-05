from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
import numpy_financial as npf
import pandas as pd
from dataclasses import dataclass
import json
import requests
import os

app = FastAPI(title="Israeli Mortgage Engine", version="1.0.0")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve the HTML interface at root
@app.get("/")
async def read_index():
    return FileResponse('static/index.html')

# Serve mortgage examples
@app.get("/mortage_examples/{filename}")
async def get_mortgage_example(filename: str):
    file_path = f"mortage_examples/{filename}"
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")

# Pydantic Models
class PaymentBreakdown(BaseModel):
    track_id: str
    track_name: str
    payment: float
    principal: float
    interest: float

class MonthlyPayment(BaseModel):
    total_payment: float
    breakdown: List[PaymentBreakdown]

class RateChangeHistory(BaseModel):
    date: str
    prime_rate: Optional[float] = None
    total_rate: float
    cpi_index: Optional[float] = None
    adjustment_factor: Optional[float] = None

class AdjustmentTrigger(BaseModel):
    trigger_type: str
    affects_tracks: List[str]
    next_update_date: Optional[str] = None
    next_reset_date: Optional[str] = None
    maturity_date: Optional[str] = None
    end_date: Optional[str] = None

class MortgageTrack(BaseModel):
    track_id: str
    track_name: str
    track_type: str
    original_amount: float
    current_balance: float
    rate: float
    rate_type: str
    start_date: str
    total_term_months: int
    remaining_months: int
    payments_made: int
    
    # Grace period specific
    grace_period_months: Optional[int] = None
    current_phase: Optional[str] = None
    is_interest_only: Optional[bool] = None
    
    # Bridge loan specific
    bridge_period_months: Optional[int] = None
    has_balloon_payment: Optional[bool] = None
    
    # Prime rate specific
    base_rate: Optional[float] = None
    margin: Optional[float] = None
    current_rate: Optional[float] = None
    rate_change_history: Optional[List[RateChangeHistory]] = None
    
    # Index linked specific
    index_type: Optional[str] = None
    base_cpi: Optional[float] = None
    current_cpi: Optional[float] = None
    cpi_adjustment_factor: Optional[float] = None
    rate_reset_frequency_years: Optional[int] = None
    next_rate_reset_date: Optional[str] = None
    cpi_update_history: Optional[List[RateChangeHistory]] = None
    
    # Bridge specific
    maturity_date: Optional[str] = None

class MarketConditions(BaseModel):
    current_prime_rate: float
    current_cpi_index: float
    base_cpi_index: float

class Borrower(BaseModel):
    name: str
    id: str

class MortgageDetails(BaseModel):
    original_amount: float
    currency: str = "ILS"
    start_date: str
    current_date: str

class AmortizationEntry(BaseModel):
    payment_number: int
    date: str
    payment: float
    principal: float
    interest: float
    balance: float

class MortgageState(BaseModel):
    mortgage_id: str
    borrower: Borrower
    mortgage_details: MortgageDetails
    market_conditions: MarketConditions
    tracks: List[MortgageTrack]
    current_monthly_payment: MonthlyPayment
    last_calculation_date: str
    next_adjustment_triggers: List[AdjustmentTrigger]
    amortization_table: Optional[List[AmortizationEntry]] = None

class MonthlyChanges(BaseModel):
    new_prime_rate: Optional[float] = None
    new_cpi_index: Optional[float] = None
    calculation_date: str

class UpdateMortgageRequest(BaseModel):
    mortgage_state: MortgageState
    monthly_changes: MonthlyChanges

class UpdateMortgageResponse(BaseModel):
    updated_mortgage_state: MortgageState
    changes_applied: Dict[str, Any]

# Core Engine Logic
class MortgageEngine:
    
    @staticmethod
    def calculate_payment(rate: float, periods: int, principal: float) -> float:
        """Calculate monthly payment using numpy financial PMT"""
        if rate == 0:
            return principal / periods
        return float(npf.pmt(rate / 12, periods, -principal))
    
    @staticmethod
    def calculate_track_payment(track: MortgageTrack, market_conditions: MarketConditions, 
                              calculation_date: str) -> PaymentBreakdown:
        """Calculate payment for a single track"""
        
        if track.remaining_months <= 0:
            return PaymentBreakdown(
                track_id=track.track_id,
                track_name=track.track_name,
                payment=0,
                principal=0,
                interest=0
            )
        
        # Determine current rate and balance
        current_rate = track.rate
        current_balance = track.current_balance
        
        # Handle different track types
        if track.track_type == "variable_prime":
            current_rate = market_conditions.current_prime_rate
            
        elif track.track_type == "index_linked_variable":
            # Adjust balance for CPI
            cpi_factor = market_conditions.current_cpi_index / market_conditions.base_cpi_index
            current_balance = track.original_amount * cpi_factor * (track.current_balance / track.original_amount)
            
        elif track.track_type == "grace_period" and track.is_interest_only:
            # Grace period - interest only
            interest = current_balance * (current_rate / 12)
            return PaymentBreakdown(
                track_id=track.track_id,
                track_name=track.track_name,
                payment=interest,
                principal=0,
                interest=interest
            )
        
        # Calculate regular payment
        monthly_payment = MortgageEngine.calculate_payment(
            current_rate, track.remaining_months, current_balance
        )
        
        # Calculate interest and principal portions
        monthly_interest = current_balance * (current_rate / 12)
        monthly_principal = monthly_payment - monthly_interest
        
        return PaymentBreakdown(
            track_id=track.track_id,
            track_name=track.track_name,
            payment=monthly_payment,
            principal=monthly_principal,
            interest=monthly_interest
        )
    
    @staticmethod
    def generate_amortization_table(track: MortgageTrack, market_conditions: MarketConditions,
                                   start_date: str, months: int = 12) -> List[AmortizationEntry]:
        """Generate amortization table for a track with grace period and bridge loan support"""
        table = []
        balance = track.current_balance
        current_date = datetime.strptime(start_date, "%Y-%m-%d")
        
        # Handle CPI adjustment for index-linked tracks
        if track.track_type == "index_linked_variable":
            cpi_factor = market_conditions.current_cpi_index / market_conditions.base_cpi_index
            balance = track.original_amount * cpi_factor * (balance / track.original_amount)
        
        current_rate = track.rate
        if track.track_type == "variable_prime":
            current_rate = market_conditions.current_prime_rate
        
        # Handle different track types
        if track.track_type == "bridge":
            # Bridge loan: interest-only + balloon payment at the end
            bridge_months = track.bridge_period_months or track.total_term_months
            monthly_interest = balance * (current_rate / 12)
            
            for i in range(min(months, bridge_months)):
                payment_num = track.payments_made + i + 1
                
                if i == bridge_months - 1:  # Last payment includes balloon
                    entry = AmortizationEntry(
                        payment_number=payment_num,
                        date=current_date.strftime("%Y-%m-%d"),
                        payment=monthly_interest + balance,  # Interest + principal balloon
                        principal=balance,  # Full principal at end
                        interest=monthly_interest,
                        balance=0  # Paid off
                    )
                    balance = 0
                else:
                    entry = AmortizationEntry(
                        payment_number=payment_num,
                        date=current_date.strftime("%Y-%m-%d"),
                        payment=monthly_interest,
                        principal=0,
                        interest=monthly_interest,
                        balance=balance  # No principal reduction
                    )
                
                table.append(entry)
                current_date = datetime(current_date.year + (current_date.month // 12), 
                                      ((current_date.month % 12) + 1), current_date.day)
        
        elif track.track_type == "grace_period":
            # Grace period: interest-only for grace months, then regular amortization
            grace_months = track.grace_period_months or 0
            total_months = min(months, track.remaining_months)
            
            for i in range(total_months):
                payment_num = track.payments_made + i + 1
                
                if i < grace_months:
                    # Grace period: interest-only
                    monthly_interest = balance * (current_rate / 12)
                    entry = AmortizationEntry(
                        payment_number=payment_num,
                        date=current_date.strftime("%Y-%m-%d"),
                        payment=monthly_interest,
                        principal=0,
                        interest=monthly_interest,
                        balance=balance
                    )
                else:
                    # After grace: regular amortization for remaining term
                    remaining_months = track.total_term_months - grace_months
                    monthly_payment = abs(npf.pmt(current_rate / 12, remaining_months, -balance))
                    interest = balance * (current_rate / 12)
                    principal = monthly_payment - interest
                    balance -= principal
                    
                    entry = AmortizationEntry(
                        payment_number=payment_num,
                        date=current_date.strftime("%Y-%m-%d"),
                        payment=monthly_payment,
                        principal=principal,
                        interest=interest,
                        balance=max(0, balance)
                    )
                
                table.append(entry)
                current_date = datetime(current_date.year + (current_date.month // 12), 
                                      ((current_date.month % 12) + 1), current_date.day)
        
        else:
            # Regular loan: standard amortization
            monthly_payment = abs(npf.pmt(current_rate / 12, track.remaining_months, -balance))
            
            for i in range(min(months, track.remaining_months)):
                interest = balance * (current_rate / 12)
                principal = monthly_payment - interest
                balance -= principal
                
                entry = AmortizationEntry(
                    payment_number=track.payments_made + i + 1,
                    date=current_date.strftime("%Y-%m-%d"),
                    payment=monthly_payment,
                    principal=principal,
                    interest=interest,
                    balance=max(0, balance)
                )
                
                table.append(entry)
                current_date = datetime(current_date.year + (current_date.month // 12), 
                                      ((current_date.month % 12) + 1), current_date.day)
        
        return table
    
    @staticmethod
    def generate_combined_amortization_table(tracks: List[MortgageTrack], market_conditions: MarketConditions,
                                           start_date: str, months: int = 12) -> List[AmortizationEntry]:
        """Generate combined amortization table for all tracks"""
        # Get individual track tables
        all_track_tables = []
        for track in tracks:
            track_table = MortgageEngine.generate_amortization_table(
                track, market_conditions, start_date, months
            )
            all_track_tables.extend(track_table)
        
        # Group by payment number and combine
        combined_payments = {}
        
        for entry in all_track_tables:
            payment_num = entry.payment_number
            
            if payment_num not in combined_payments:
                combined_payments[payment_num] = {
                    'payment_number': payment_num,
                    'date': entry.date,
                    'payment': 0.0,
                    'principal': 0.0,
                    'interest': 0.0,
                    'balance': 0.0
                }
            
            combined_payments[payment_num]['payment'] += entry.payment
            combined_payments[payment_num]['principal'] += entry.principal
            combined_payments[payment_num]['interest'] += entry.interest
            combined_payments[payment_num]['balance'] += entry.balance
        
        # Convert to AmortizationEntry objects and sort
        combined_table = []
        for payment_num in sorted(combined_payments.keys()):
            data = combined_payments[payment_num]
            combined_table.append(AmortizationEntry(
                payment_number=data['payment_number'],
                date=data['date'],
                payment=round(data['payment'], 2),
                principal=round(data['principal'], 2),
                interest=round(data['interest'], 2),
                balance=round(data['balance'], 2)
            ))
        
        return combined_table
    
    @staticmethod
    def update_mortgage_state(mortgage_state: MortgageState, 
                            monthly_changes: MonthlyChanges) -> tuple[MortgageState, Dict[str, Any]]:
        """Update mortgage state with new market conditions"""
        
        changes_applied = {}
        
        # Update market conditions
        new_market_conditions = mortgage_state.market_conditions.model_copy()
        
        if monthly_changes.new_prime_rate is not None:
            changes_applied["prime_rate_change"] = {
                "old": new_market_conditions.current_prime_rate,
                "new": monthly_changes.new_prime_rate
            }
            new_market_conditions.current_prime_rate = monthly_changes.new_prime_rate
        
        if monthly_changes.new_cpi_index is not None:
            changes_applied["cpi_change"] = {
                "old": new_market_conditions.current_cpi_index,
                "new": monthly_changes.new_cpi_index
            }
            new_market_conditions.current_cpi_index = monthly_changes.new_cpi_index
        
        # Calculate new payments for each track
        payment_breakdown = []
        total_payment = 0
        
        for track in mortgage_state.tracks:
            breakdown = MortgageEngine.calculate_track_payment(
                track, new_market_conditions, monthly_changes.calculation_date
            )
            payment_breakdown.append(breakdown)
            total_payment += breakdown.payment
        
        # Generate combined amortization table (ALL remaining months)
        max_months = max([track.remaining_months for track in mortgage_state.tracks] + [0])
        amortization_table = MortgageEngine.generate_combined_amortization_table(
            mortgage_state.tracks, new_market_conditions, monthly_changes.calculation_date, max_months
        )
        
        # Create updated mortgage state
        updated_state = mortgage_state.model_copy()
        updated_state.market_conditions = new_market_conditions
        updated_state.current_monthly_payment = MonthlyPayment(
            total_payment=total_payment,
            breakdown=payment_breakdown
        )
        updated_state.last_calculation_date = monthly_changes.calculation_date
        updated_state.amortization_table = amortization_table
        
        return updated_state, changes_applied

# API Endpoints
@app.post("/update-mortgage", response_model=UpdateMortgageResponse)
async def update_mortgage(request: UpdateMortgageRequest):
    """
    Update mortgage state with new market conditions and calculate new payments
    """
    try:
        updated_state, changes = MortgageEngine.update_mortgage_state(
            request.mortgage_state, request.monthly_changes
        )
        
        return UpdateMortgageResponse(
            updated_mortgage_state=updated_state,
            changes_applied=changes
        )
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating mortgage: {str(e)}")

@app.get("/api/health")
async def health_check():
    return {"message": "Israeli Mortgage Engine API", "version": "1.0.0", "status": "healthy"}

class BankComparisonRequest(BaseModel):
    loan_value: str
    loan_years: int
    loan_interest: str

@app.post("/proxy-bank-api")
async def proxy_bank_jerusalem_api(request: BankComparisonRequest):
    """
    Proxy endpoint to call Bank Jerusalem API (avoids CORS issues)
    """
    try:
        # Prepare the data exactly as Bank Jerusalem expects it
        bank_data = {
            "mix": json.dumps([
                {
                    "loan_board": "1",
                    "loan_type": "1|0",
                    "loan_value": request.loan_value,
                    "loan_years": request.loan_years,
                    "loan_interest": request.loan_interest,
                    "update_interest": 0
                },
                {
                    "loan_board": "1",
                    "loan_type": "1|0", 
                    "loan_value": "",
                    "loan_years": 0,
                    "loan_interest": "",
                    "update_interest": 0
                },
                {
                    "loan_board": "1",
                    "loan_type": "1|0",
                    "loan_value": "",
                    "loan_years": 0,
                    "loan_interest": "",
                    "update_interest": 0
                }
            ])
        }
        
        # Call Bank Jerusalem API with all required headers
        response = requests.post(
            "https://calculator.bankjerusalem.co.il/jerusalem/api_calc",
            headers={
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'en-US,en;q=0.9,he;q=0.8',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Origin': 'https://calculator.bankjerusalem.co.il',
                'Pragma': 'no-cache',
                'Referer': 'https://calculator.bankjerusalem.co.il/',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
                'X-Requested-With': 'XMLHttpRequest',
                'sec-ch-ua': '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"'
            },
            data=bank_data,
            timeout=10
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Bank API returned: {response.status_code}")
            
        # Try to parse JSON response
        try:
            bank_result = response.json()
        except json.JSONDecodeError:
            # If JSON parsing fails, return the raw text for debugging
            return {
                "success": False,
                "error": "Invalid JSON response from bank",
                "raw_response": response.text[:500]  # First 500 chars for debugging
            }
        
        return {
            "success": True,
            "bank_result": bank_result,
            "status_code": response.status_code
        }
        
    except requests.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Failed to connect to Bank Jerusalem API: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")

class PaymentCalculationRequest(BaseModel):
    rate: float
    periods: int
    principal: float

@app.post("/calculate-payment")
async def calculate_payment(request: PaymentCalculationRequest):
    """
    Simple payment calculation endpoint
    """
    try:
        payment = MortgageEngine.calculate_payment(request.rate, request.periods, request.principal)
        return {"monthly_payment": payment}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error calculating payment: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
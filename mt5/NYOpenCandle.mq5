//+------------------------------------------------------------------+
//| NYOpenCandle.mq5                                                 |
//| Trades the NAS100 New York open-candle rule from trading-ai-bot. |
//| Attach to a US100 / NAS100 / USTEC chart (any timeframe).        |
//| One trade a day: the 09:30 New York 5-minute candle vs the 8 EMA,|
//| with the 300 EMA as the trend filter. Stop at the candle extreme,|
//| breakeven at +1R, 3.5 x ATR chandelier trail after +1R,          |
//| flat at 15:30 New York. Risk is a % of the starting balance,     |
//| halved after 30% and quartered after 60% of the max loss is used.|
//+------------------------------------------------------------------+
#property copyright "trading-ai-bot"
#property version   "1.00"
#property description "NAS100 New York open-candle rule with prop-firm sizing"

#include <Trade/Trade.mqh>

input double RiskPct         = 0.75;    // Base risk per trade, % of StartBalance
input double StartBalance    = 100000;  // The account's starting balance (the firm's account size)
input double MaxLossPct      = 10.0;    // Firm's max loss, % of StartBalance (static)
input double DailyStopPct    = 4.0;     // Stop for the day at this loss (firm limit is usually 5%)
input bool   UseDrawdownCut  = true;    // Halve risk at 30% of max loss used, quarter it at 60%
input int    EmaFast         = 8;       // Signal EMA (5-minute)
input int    EmaSlow         = 300;     // Trend EMA (5-minute)
input int    AtrLen          = 14;      // ATR length for the trail (Wilder)
input double AtrMult         = 3.5;     // Chandelier distance in ATRs
input double BreakevenR      = 1.0;     // Move stop to entry at this many R
input double TrailAfterR     = 1.0;     // Start the chandelier trail at this many R
input double MinBodyR        = 0.1;     // Skip if the close is within this many R of the fast EMA
input double MinRiskPoints   = 5.0;     // Skip if the stop is closer than this (index points)
input int    SignalHHMM      = 930;     // New York time of the signal candle
input int    ExitHHMM        = 1530;    // New York time to close any open trade
input int    ServerMinusNY   = 0;       // 0 = auto (live). In the Strategy Tester set it, e.g. 7 for "New York close" brokers
input long   Magic           = 93035;

CTrade   trade;
int      hFast = INVALID_HANDLE, hSlow = INVALID_HANDLE;
datetime lastBar = 0;
int      lastTradeDay = 0;
int      equityDay = 0;
double   dayStartEquity = 0;

//--- state of the open trade, persisted in terminal global variables so a restart does not lose it
double gEntry = 0, gRisk = 0, gBest = 0; int gDir = 0;
string GV(string k) { return "NYOC_" + _Symbol + "_" + IntegerToString(Magic) + "_" + k; }
void SaveState() { GlobalVariableSet(GV("entry"), gEntry); GlobalVariableSet(GV("risk"), gRisk); GlobalVariableSet(GV("best"), gBest); GlobalVariableSet(GV("dir"), gDir); GlobalVariableSet(GV("day"), lastTradeDay); }
void LoadState() {
   if(GlobalVariableCheck(GV("entry"))) { gEntry = GlobalVariableGet(GV("entry")); gRisk = GlobalVariableGet(GV("risk")); gBest = GlobalVariableGet(GV("best")); gDir = (int)GlobalVariableGet(GV("dir")); lastTradeDay = (int)GlobalVariableGet(GV("day")); }
}

//--- New York time --------------------------------------------------
datetime NthSunday(int y, int m, int n) {
   MqlDateTime t; ZeroMemory(t); t.year = y; t.mon = m; t.day = 1;
   datetime d = StructToTime(t); TimeToStruct(d, t);
   int first = 1 + (7 - t.day_of_week) % 7;
   t.day = first + 7 * (n - 1); t.hour = 0; t.min = 0; t.sec = 0;
   return StructToTime(t);
}
bool IsUsDst(datetime gmt) {
   MqlDateTime t; TimeToStruct(gmt, t);
   datetime start = NthSunday(t.year, 3, 2) + 7 * 3600;   // 02:00 EST
   datetime end   = NthSunday(t.year, 11, 1) + 6 * 3600;  // 02:00 EDT
   return gmt >= start && gmt < end;
}
int ServerMinusNYHours() {
   if(ServerMinusNY != 0) return ServerMinusNY;
   datetime gmt = TimeGMT();
   int serverMinusGmt = (int)MathRound((double)(TimeTradeServer() - gmt) / 1800.0) * 1800;
   int nyMinusGmt = IsUsDst(gmt) ? -4 * 3600 : -5 * 3600;
   return (serverMinusGmt - nyMinusGmt) / 3600;
}
datetime ToNY(datetime server) { return server - ServerMinusNYHours() * 3600; }
int HHMM(datetime t) { MqlDateTime m; TimeToStruct(t, m); return m.hour * 100 + m.min; }
int YMD(datetime t)  { MqlDateTime m; TimeToStruct(t, m); return m.year * 10000 + m.mon * 100 + m.day; }

//--- indicators -----------------------------------------------------
double Buf(int handle, int shift) { double b[]; if(CopyBuffer(handle, 0, shift, 1, b) != 1) return EMPTY_VALUE; return b[0]; }
double WilderATR(int shift) {
   int n = AtrLen * 12 + 2;
   MqlRates r[]; ArraySetAsSeries(r, true);
   if(CopyRates(_Symbol, PERIOD_M5, shift, n, r) != n) return EMPTY_VALUE;
   double a = 0; bool seeded = false;
   for(int i = n - 2; i >= 0; i--) {
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i + 1].close), MathAbs(r[i].low - r[i + 1].close)));
      if(!seeded) { a = tr; seeded = true; } else a += (tr - a) / AtrLen;
   }
   return a;
}

//--- position helpers -----------------------------------------------
bool SelectOurPosition() {
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong tk = PositionGetTicket(i);
      if(tk > 0 && PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == Magic) return true;
   }
   return false;
}
double RiskMultiplier() {
   if(!UseDrawdownCut) return 1.0;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double used = (StartBalance - eq) / (StartBalance * MaxLossPct / 100.0);
   if(used >= 0.6) return 0.25;
   if(used >= 0.3) return 0.5;
   return 1.0;
}
double LotsFor(double stopDistance) {
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP), vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(tickValue <= 0 || tickSize <= 0 || stopDistance <= 0) return 0;
   double money = StartBalance * RiskPct / 100.0 * RiskMultiplier();
   double perLotPerPrice = tickValue / tickSize;
   double lots = MathFloor(money / (stopDistance * perLotPerPrice) / step) * step;
   if(lots < vmin) return 0;
   return MathMin(lots, vmax);
}

//--- lifecycle ------------------------------------------------------
int OnInit() {
   trade.SetExpertMagicNumber(Magic);
   trade.SetTypeFillingBySymbol(_Symbol);
   hFast = iMA(_Symbol, PERIOD_M5, EmaFast, 0, MODE_EMA, PRICE_CLOSE);
   hSlow = iMA(_Symbol, PERIOD_M5, EmaSlow, 0, MODE_EMA, PRICE_CLOSE);
   if(hFast == INVALID_HANDLE || hSlow == INVALID_HANDLE) { Print("indicator handles failed"); return INIT_FAILED; }
   LoadState();
   PrintFormat("NYOpenCandle ready on %s. Server - New York = %d h. Risk %.2f%% of %.0f.", _Symbol, ServerMinusNYHours(), RiskPct, StartBalance);
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason) { if(hFast != INVALID_HANDLE) IndicatorRelease(hFast); if(hSlow != INVALID_HANDLE) IndicatorRelease(hSlow); }

void OnTick() {
   datetime t0 = iTime(_Symbol, PERIOD_M5, 0);
   if(t0 == 0 || t0 == lastBar) return;
   lastBar = t0;
   OnNewBar(t0);
}

void OnNewBar(datetime t0) {
   datetime ny0 = ToNY(t0);
   int today = YMD(ny0);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(today != equityDay) { equityDay = today; dayStartEquity = eq; }

   // hard safety: never trade below the max-loss line or after the daily stop
   bool dailyStopped = eq <= dayStartEquity * (1.0 - DailyStopPct / 100.0);
   bool dead = eq <= StartBalance * (1.0 - MaxLossPct / 100.0) * 1.002;

   if(SelectOurPosition()) { Manage(ny0, dailyStopped || dead); return; }
   gDir = 0;
   if(dead || dailyStopped || lastTradeDay == today) return;

   // the bar that just closed must be the 09:30 New York candle
   datetime t1 = iTime(_Symbol, PERIOD_M5, 1);
   if(HHMM(ToNY(t1)) != SignalHHMM || YMD(ToNY(t1)) != today) return;
   MqlRates r[]; ArraySetAsSeries(r, true);
   if(CopyRates(_Symbol, PERIOD_M5, 1, 1, r) != 1) return;
   double fast = Buf(hFast, 1), slow = Buf(hSlow, 1);
   if(fast == EMPTY_VALUE || slow == EMPTY_VALUE) return;
   double c = r[0].close;
   int dir = 0;
   if(c > fast && c > slow) dir = 1;
   else if(c < fast && c < slow) dir = -1;
   if(dir == 0) { lastTradeDay = today; SaveState(); Print("no trade: close not on the same side of both EMAs"); return; }
   double stop = dir > 0 ? r[0].low : r[0].high;
   double riskBt = MathAbs(c - stop);
   if(riskBt < MinRiskPoints) { lastTradeDay = today; SaveState(); Print("no trade: candle too small"); return; }
   if(MathAbs(c - fast) / riskBt < MinBodyR) { lastTradeDay = today; SaveState(); Print("no trade: close too close to the EMA"); return; }

   double px = dir > 0 ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double dist = (px - stop) * dir;
   if(dist <= 0) { lastTradeDay = today; SaveState(); Print("no trade: price already through the stop"); return; }
   double lots = LotsFor(dist);
   if(lots <= 0) { lastTradeDay = today; SaveState(); Print("no trade: size below the broker minimum"); return; }
   bool ok = dir > 0 ? trade.Buy(lots, _Symbol, 0, stop, 0, "NYOC") : trade.Sell(lots, _Symbol, 0, stop, 0, "NYOC");
   lastTradeDay = today;
   if(ok && SelectOurPosition()) {
      gDir = dir; gEntry = PositionGetDouble(POSITION_PRICE_OPEN); gRisk = MathAbs(gEntry - stop);
      gBest = dir > 0 ? r[0].high : r[0].low;
      PrintFormat("%s %.2f lots at %.2f, stop %.2f (%.1f points, %.2f%% risk)", dir > 0 ? "BUY" : "SELL", lots, gEntry, stop, gRisk, RiskPct * RiskMultiplier());
   } else PrintFormat("order failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   SaveState();
}

void Manage(datetime ny0, bool forceClose) {
   ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
   int dir = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
   if(gDir == 0) { gDir = dir; gEntry = PositionGetDouble(POSITION_PRICE_OPEN); gRisk = MathAbs(gEntry - PositionGetDouble(POSITION_SL)); gBest = gEntry; }
   if(forceClose || HHMM(ny0) >= ExitHHMM) { trade.PositionClose(ticket); Print(forceClose ? "closed: safety stop" : "closed: 15:30 New York"); gDir = 0; SaveState(); return; }
   if(gRisk <= 0) return;

   MqlRates r[]; ArraySetAsSeries(r, true);
   if(CopyRates(_Symbol, PERIOD_M5, 1, 1, r) != 1) return;
   gBest = dir > 0 ? MathMax(gBest, r[0].high) : MathMin(gBest, r[0].low);
   double openR = (r[0].close - gEntry) * dir / gRisk;
   double sl = PositionGetDouble(POSITION_SL), newSl = sl;
   if(BreakevenR > 0 && openR >= BreakevenR) newSl = dir > 0 ? MathMax(newSl, gEntry) : MathMin(newSl, gEntry);
   if(openR >= TrailAfterR) {
      double a = WilderATR(1);
      if(a != EMPTY_VALUE) { double lvl = gBest - dir * AtrMult * a; newSl = dir > 0 ? MathMax(newSl, lvl) : MathMin(newSl, lvl); }
   }
   if(MathAbs(newSl - sl) > SymbolInfoDouble(_Symbol, SYMBOL_POINT)) {
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double minGap = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(_Symbol, SYMBOL_POINT);
      bool valid = dir > 0 ? newSl < bid - minGap : newSl > ask + minGap;
      if(valid) trade.PositionModify(ticket, NormalizeDouble(newSl, _Digits), 0);
      else { trade.PositionClose(ticket); Print("closed: price already through the new stop"); gDir = 0; }
   }
   SaveState();
}
//+------------------------------------------------------------------+

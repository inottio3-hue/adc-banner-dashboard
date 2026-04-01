import streamlit as st
import pandas as pd
import requests
import datetime
import calendar
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ページ設定
st.set_page_config(page_title="案件進捗管理ダッシュボード", layout="wide")

# タイトル
st.title("📊 案件進捗管理ダッシュボード")

# --- サイドバー設定 ---
st.sidebar.header("設定 / フィルタ")

# 1. API Key入力
api_key = st.sidebar.text_input("MicroAd API Key", type="password")

# 2. 期間選択モード
today = datetime.date.today()
period_mode = st.sidebar.radio("期間モード", ["月度選択", "カスタム期間"], horizontal=True)

if period_mode == "月度選択":
    # 過去12ヶ月分の選択肢を生成
    month_options = []
    for i in range(12):
        d = today.replace(day=1) - datetime.timedelta(days=i * 28)
        d = d.replace(day=1)
        month_options.append(d.strftime("%Y年%m月"))
    # 重複除去して日付順に
    month_options = list(dict.fromkeys(month_options))
    selected_month = st.sidebar.selectbox("月度を選択", month_options)
    sel_year = int(selected_month[:4])
    sel_month = int(selected_month[5:7])
    start_date = datetime.date(sel_year, sel_month, 1)
    _, last_day = calendar.monthrange(sel_year, sel_month)
    end_date = datetime.date(sel_year, sel_month, last_day)
    # 未来の場合は昨日まで
    if end_date >= today:
        end_date = today - datetime.timedelta(days=1)
    st.sidebar.info(f"📅 {start_date} ～ {end_date}")
else:
    first_day = today.replace(day=1)
    start_date = st.sidebar.date_input("開始日", first_day)
    # 月初1日に開いた場合は1日、それ以外は前日
    if today.day == 1:
        default_end = today
    else:
        default_end = today - datetime.timedelta(days=1)
    end_date = st.sidebar.date_input("終了日", default_end)

# --- データ取得関数 ---
def get_microad_data(api_key, start, end):
    url = "https://report.ads-api.universe.microad.jp/v2/reports"
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "start_date": start.strftime("%Y%m%d"),
        "end_date": end.strftime("%Y%m%d"),
        "report_type": "campaign"
    }
    try:
        response = requests.request("GET", url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return None

# --- 色分けロジック ---
def color_diff_pacing(val):
    if val > 10: return 'color: blue; font-weight: bold;'
    elif 0 <= val <= 10: return 'color: black;'
    elif -10 <= val < 0: return 'color: #D4AC0D; font-weight: bold;'
    else: return 'color: red; font-weight: bold;'

def color_day_diff(val):
    if val > 0: return 'color: blue; font-weight: bold;'
    elif val < 0: return 'color: red; font-weight: bold;'
    else: return 'color: black;'

# --- メイン処理 ---
if st.sidebar.button("データ取得"):
    if not api_key:
        st.warning("API Keyを入力してください。")
    else:
        with st.spinner("データを取得中..."):
            data = get_microad_data(api_key, start_date, end_date)
            
        if data:
            # 1. マスタ作成
            campaigns = []
            if 'account' in data:
                for acc in data['account']:
                    acc_name = acc.get('name', 'Unknown')
                    if 'campaign' in acc:
                        for camp in acc['campaign']:
                            target_month = start_date.strftime("%Y%m")
                            monthly_limit = 0
                            if 'campaign_monthly_charge_limit' in camp:
                                for limit in camp['campaign_monthly_charge_limit']:
                                    if limit.get('month') == target_month:
                                        monthly_limit = limit.get('charge_limit', 0)
                                        break
                            campaigns.append({
                                'campaign_id': camp['id'],
                                'account_name': acc_name,
                                'campaign_name': camp['name'],
                                'monthly_budget': monthly_limit
                            })
            master_df = pd.DataFrame(campaigns)

            # ========================================================
            # 月度選択モード：専用の月次サマリ表示
            # ========================================================
            if period_mode == "月度選択":
                records = []
                if 'report' in data and 'records' in data['report']:
                    records = data['report']['records']
                
                if not records:
                    st.warning("指定月のデータがありません。")
                else:
                    perf_df = pd.DataFrame(records)
                    for col in ['net', 'gross', 'impression', 'click']:
                        if col in perf_df.columns:
                            perf_df[col] = pd.to_numeric(perf_df[col], errors='coerce').fillna(0)
                    
                    # キャンペーン別集計
                    agg_df = perf_df.groupby('campaign_id')[['gross', 'impression', 'click']].sum().reset_index()
                    merged_df = pd.merge(agg_df, master_df, on='campaign_id', how='left')
                    merged_df['remaining'] = merged_df['monthly_budget'] - merged_df['gross']
                    merged_df['progress_pct'] = merged_df.apply(
                        lambda x: (x['gross'] / x['monthly_budget'] * 100) if x['monthly_budget'] > 0 else 0, axis=1)
                    
                    # --- 全体サマリ ---
                    st.markdown("---")
                    st.markdown(f"### 📅 {selected_month} 月次レポート")
                    
                    total_budget = merged_df['monthly_budget'].sum()
                    total_gross = merged_df['gross'].sum()
                    total_remaining = total_budget - total_gross
                    
                    mc1, mc2, mc3 = st.columns(3)
                    mc1.metric("① 当月予算", f"¥{total_budget:,.0f}")
                    mc2.metric("② 当月消化額", f"¥{total_gross:,.0f}",
                               delta=f"消化率 {total_gross/total_budget*100:.1f}%" if total_budget > 0 else "")
                    mc3.metric("③ 未消化額（消化残額）", f"¥{total_remaining:,.0f}",
                               delta=f"残 {total_remaining/total_budget*100:.1f}%" if total_budget > 0 else "")
                    
                    # --- アカウント別サマリ ---
                    st.markdown("---")
                    st.markdown("#### 📋 アカウント別 月次サマリ")
                    
                    acc_summary = merged_df.groupby('account_name').agg(
                        monthly_budget=('monthly_budget', 'sum'),
                        gross=('gross', 'sum'),
                        remaining=('remaining', 'sum'),
                        impression=('impression', 'sum'),
                        click=('click', 'sum')
                    ).reset_index()
                    acc_summary['progress_pct'] = acc_summary.apply(
                        lambda x: (x['gross'] / x['monthly_budget'] * 100) if x['monthly_budget'] > 0 else 0, axis=1)
                    acc_summary['ctr'] = acc_summary.apply(
                        lambda x: (x['click'] / x['impression'] * 100) if x['impression'] > 0 else 0, axis=1)
                    
                    acc_display = acc_summary[['account_name', 'monthly_budget', 'gross', 'remaining', 'progress_pct', 'impression', 'click', 'ctr']].copy()
                    acc_display.columns = ['アカウント名', '① 当月予算', '② 当月消化額', '③ 未消化額', '消化率(%)', '合計IMP', '合計Click', 'CTR(%)']
                    
                    styled_acc = acc_display.style.format({
                        '① 当月予算': '¥{:,.0f}',
                        '② 当月消化額': '¥{:,.0f}',
                        '③ 未消化額': '¥{:,.0f}',
                        '消化率(%)': '{:.1f}%',
                        '合計IMP': '{:,.0f}',
                        '合計Click': '{:,.0f}',
                        'CTR(%)': '{:.2f}%'
                    })
                    st.dataframe(styled_acc, use_container_width=True, height=400)
                    
                    # --- キャンペーン別詳細 ---
                    st.markdown("#### 📋 キャンペーン別 詳細")
                    
                    camp_display = merged_df[['account_name', 'campaign_name', 'monthly_budget', 'gross', 'remaining', 'progress_pct', 'impression', 'click']].copy()
                    camp_display['ctr'] = camp_display.apply(
                        lambda x: (x['click'] / x['impression'] * 100) if x['impression'] > 0 else 0, axis=1)
                    camp_display.columns = ['アカウント名', 'キャンペーン名', '① 当月予算', '② 当月消化額', '③ 未消化額', '消化率(%)', '合計IMP', '合計Click', 'CTR(%)']
                    
                    styled_camp = camp_display.style.format({
                        '① 当月予算': '¥{:,.0f}',
                        '② 当月消化額': '¥{:,.0f}',
                        '③ 未消化額': '¥{:,.0f}',
                        '消化率(%)': '{:.1f}%',
                        '合計IMP': '{:,.0f}',
                        '合計Click': '{:,.0f}',
                        'CTR(%)': '{:.2f}%'
                    })
                    st.dataframe(styled_camp, use_container_width=True, height=600)
                
                st.stop()  # 月度選択モードはここで終了（カスタム期間の詳細画面は表示しない）

            # 2. 実績データ作成
            records = []
            if 'report' in data and 'records' in data['report']:
                records = data['report']['records']
            
            if not records:
                st.warning("指定期間の配信実績データがありません。")
            else:
                perf_df = pd.DataFrame(records)
                numeric_cols = ['net', 'gross', 'impression', 'click']
                for col in numeric_cols:
                    if col in perf_df.columns:
                        perf_df[col] = pd.to_numeric(perf_df[col], errors='coerce').fillna(0)
                
                if 'target_date' in perf_df.columns:
                    perf_df['target_date'] = pd.to_datetime(perf_df['target_date'].astype(str))
                
                # 集計処理
                agg_df = perf_df.groupby('campaign_id')[numeric_cols].sum().reset_index()
                
                # 前日比計算
                if 'target_date' in perf_df.columns and not perf_df.empty:
                    latest_date = perf_df['target_date'].max()
                    prev_date = latest_date - datetime.timedelta(days=1)
                    
                    target_cols = ['gross', 'impression', 'click']
                    latest_df = perf_df[perf_df['target_date'] == latest_date].groupby('campaign_id')[target_cols].sum().reset_index()
                    prev_df = perf_df[perf_df['target_date'] == prev_date].groupby('campaign_id')[target_cols].sum().reset_index()
                    
                    latest_df = latest_df.rename(columns={'gross':'l_gross', 'impression':'l_imp', 'click':'l_click'})
                    prev_df = prev_df.rename(columns={'gross':'p_gross', 'impression':'p_imp', 'click':'p_click'})
                    
                    # --- CTR計算 ---
                    latest_df['l_ctr'] = (latest_df['l_click'] / latest_df['l_imp'] * 100).fillna(0)
                    prev_df['p_ctr'] = (prev_df['p_click'] / prev_df['p_imp'] * 100).fillna(0)
                    
                    daily_diff_df = pd.merge(latest_df, prev_df, on='campaign_id', how='left').fillna(0)
                    daily_diff_df['diff_gross'] = daily_diff_df['l_gross'] - daily_diff_df['p_gross']
                    daily_diff_df['diff_imp'] = daily_diff_df['l_imp'] - daily_diff_df['p_imp']
                    daily_diff_df['diff_click'] = daily_diff_df['l_click'] - daily_diff_df['p_click']
                    daily_diff_df['diff_ctr'] = daily_diff_df['l_ctr'] - daily_diff_df['p_ctr']
                    
                    daily_diff_df = daily_diff_df[[
                        'campaign_id', 
                        'l_gross', 'diff_gross', 
                        'l_imp', 'diff_imp', 
                        'l_click', 'diff_click',
                        'l_ctr', 'diff_ctr'
                    ]]
                    daily_diff_df = daily_diff_df.rename(columns={
                        'l_gross':'latest_gross', 
                        'l_imp':'latest_imp', 
                        'l_click':'latest_click',
                        'l_ctr':'latest_ctr'
                    })
                else:
                    daily_diff_df = pd.DataFrame(columns=[
                        'campaign_id', 'latest_gross', 'diff_gross', 
                        'latest_imp', 'diff_imp', 'latest_click', 'diff_click', 
                        'latest_ctr', 'diff_ctr'
                    ])

                # 結合
                merged_df = pd.merge(agg_df, master_df, on='campaign_id', how='left')
                merged_df = pd.merge(merged_df, daily_diff_df, on='campaign_id', how='left')
                
                # 進捗計算
                year = end_date.year
                month = end_date.month
                _, num_days_in_month = calendar.monthrange(year, month)
                days_elapsed = end_date.day
                standard_pacing = (days_elapsed / num_days_in_month) * 100
                
                merged_df['progress_percent'] = merged_df.apply(lambda x: (x['gross']/x['monthly_budget']*100) if x['monthly_budget']>0 else 0, axis=1)
                merged_df['daily_progress_diff'] = merged_df.apply(lambda x: (x['latest_gross']/x['monthly_budget']*100) if x['monthly_budget']>0 else 0, axis=1)
                merged_df['diff_point'] = merged_df['progress_percent'] - standard_pacing
                
                merged_df['period_ctr'] = merged_df.apply(lambda x: (x['click'] / x['impression'] * 100) if x['impression'] > 0 else 0, axis=1)

                # 昨日予定消化額 = (当月予算 - 期間消化額) ÷ 当月残日数（昨日含む）
                # end_date = 昨日の日付。当月残日数は end_date を含む残日数
                remaining_days_from_yesterday = num_days_in_month - end_date.day + 1
                merged_df['planned_daily_spend'] = merged_df.apply(
                    lambda x: (x['monthly_budget'] - x['gross']) / remaining_days_from_yesterday
                    if remaining_days_from_yesterday > 0 and x['monthly_budget'] > 0 else 0, axis=1)
                
                # 実績差異 = 昨日消化額 - 昨日予定消化額
                merged_df['spend_variance'] = merged_df['latest_gross'] - merged_df['planned_daily_spend']

                # 表示用DF
                display_df = merged_df[[
                    'account_name', 'campaign_name', 'monthly_budget', 'gross', 
                    'progress_percent', 'daily_progress_diff', 'diff_point',
                    'latest_gross', 'planned_daily_spend', 'spend_variance', 'diff_gross', 
                    'impression', 'click', 'period_ctr',
                    'latest_imp', 'diff_imp', 
                    'latest_click', 'diff_click',
                    'latest_ctr', 'diff_ctr'
                ]].copy()
                
                display_df.columns = [
                    'アカウント名', 'キャンペーン名', '当月予算', '期間消化額', 
                    '進捗率(%)', '進捗前日比', '乖離(pt)',
                    '昨日消化', '昨日予定消化額', '実績差異', '消化前日比', 
                    '期間IMP', '期間Click', '期間CTR',
                    '昨日IMP', 'IMP前日比', 
                    '昨日Click', 'Click前日比',
                    '昨日CTR', 'CTR前日比'
                ]

                table_display_df = display_df.copy()

                # --- 全体サマリ ---
                st.markdown("---")
                
                st.markdown("##### 💰 予算・消化状況（全体）")
                r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns(6)
                
                total_budget = table_display_df['当月予算'].sum()
                total_gross = table_display_df['期間消化額'].sum()
                total_remaining = total_budget - total_gross
                
                r1c1.metric("① 当月予算合計", f"¥{total_budget:,.0f}")
                r1c2.metric("② 当月消化額 (Gross)", f"¥{total_gross:,.0f}")
                r1c3.metric("③ 未消化額（消化残額）", f"¥{total_remaining:,.0f}", delta=f"{total_remaining/total_budget*100:.1f}% 残" if total_budget > 0 else "")
                r1c4.metric("昨日の合計消化額", f"¥{table_display_df['昨日消化'].sum():,.0f}", f"{table_display_df['消化前日比'].sum():+,.0f} 円")
                r1c5.metric("当月の理想進捗率", f"{standard_pacing:.1f}%", f"{end_date.month}/{end_date.day} 時点")
                avg_prog = table_display_df[table_display_df['当月予算']>0]['進捗率(%)'].mean()
                r1c6.metric("平均実績進捗率", f"{avg_prog:.1f}%", delta=f"{avg_prog - standard_pacing:.1f} pt")

                st.markdown("##### 🚨 予測・アラート")
                period_days_so_far = (end_date - start_date).days + 1
                if period_days_so_far < 1: period_days_so_far = 1
                
                avg_daily_burn = total_gross / period_days_so_far
                remaining_budget = total_budget - total_gross
                
                a1, a2, a3, a4 = st.columns(4)
                if avg_daily_burn > 0:
                    days_to_exhaustion = remaining_budget / avg_daily_burn
                    if days_to_exhaustion < (num_days_in_month - days_elapsed):
                        a1.error(f"あと {days_to_exhaustion:.1f} 日で枯渇")
                    else:
                        a1.metric("予算枯渇予測", f"あと {days_to_exhaustion:.1f} 日")
                else:
                    a1.metric("予算枯渇予測", "消化なし")

                st.markdown("##### 👁️ インプレッション・クリック状況 (全体合計)")
                r2c1, r2c2, r2c3, r2c4 = st.columns(4)
                r2c1.metric("期間合計IMP", f"{table_display_df['期間IMP'].sum():,.0f}")
                r2c2.metric("期間合計Click", f"{table_display_df['期間Click'].sum():,.0f}")
                r2c3.metric("昨日のIMP", f"{table_display_df['昨日IMP'].sum():,.0f}", f"{table_display_df['IMP前日比'].sum():+,.0f}")
                r2c4.metric("昨日のClick", f"{table_display_df['昨日Click'].sum():,.0f}", f"{table_display_df['Click前日比'].sum():+,.0f}")

                st.markdown("##### 📊 平均指標・効率 (全体平均)")
                r3c1, r3c2, r3c3, r3c4 = st.columns(4)
                
                total_imp = table_display_df['期間IMP'].sum()
                total_click = table_display_df['期間Click'].sum()
                
                daily_avg_imp = total_imp / period_days_so_far
                daily_avg_click = total_click / period_days_so_far
                ctr = (total_click / total_imp * 100) if total_imp > 0 else 0
                cpm = (total_gross / total_imp * 1000) if total_imp > 0 else 0
                
                r3c1.metric("平均IMP (日別)", f"{daily_avg_imp:,.0f}")
                r3c2.metric("平均Click (日別)", f"{daily_avg_click:,.0f}")
                r3c3.metric("平均CTR", f"{ctr:.2f}%")
                r3c4.metric("平均CPM (仕入単価)", f"¥{cpm:,.0f}")

                # --- 詳細テーブル ---
                st.markdown("---")
                st.markdown("### 📋 キャンペーン別詳細")
                st.caption("乖離： 🟦ハイペース(>+10) | ⬛順調 | 🟨警戒 | 🟥危険(<-10)")
                st.info("💡 **表の右上にある虫眼鏡マーク🔍** や列名をクリックすることで、表の中で検索・並べ替えができます。")
                
                styled_df = table_display_df.style.format({
                    '当月予算': '¥{:,.0f}', '期間消化額': '¥{:,.0f}',
                    '進捗率(%)': '{:.1f}%', '進捗前日比': '{:+.1f}pt', '乖離(pt)': '{:+.1f}',
                    '昨日消化': '¥{:,.0f}', '昨日予定消化額': '¥{:,.0f}', '実績差異': '¥{:+,.0f}',
                    '消化前日比': '{:+,.0f}',
                    '期間IMP': '{:,.0f}', '期間Click': '{:,.0f}', '期間CTR': '{:.2f}%',
                    '昨日IMP': '{:,.0f}', 'IMP前日比': '{:+,.0f}',
                    '昨日Click': '{:,.0f}', 'Click前日比': '{:+,.0f}',
                    '昨日CTR': '{:.2f}%', 'CTR前日比': '{:+.2f}pt'
                }).map(color_diff_pacing, subset=['乖離(pt)'])\
                  .map(color_day_diff, subset=['消化前日比', 'IMP前日比', 'Click前日比', 'CTR前日比', '実績差異'])

                st.dataframe(styled_df, use_container_width=True, height=600)

                # ========================================================
                # 📈 グラフ描画セクション
                # ========================================================
                st.markdown("---")
                st.markdown("### 📈 詳細分析（グラフ）")
                
                account_list = sorted(master_df['account_name'].unique())
                campaign_list = sorted(master_df['campaign_name'].unique())
                
                graph_options = ["全体合計"] + \
                                [f"【アカウント】{acc}" for acc in account_list] + \
                                [f"【キャンペーン】{camp}" for camp in campaign_list]
                
                selected_graph_item = st.selectbox("グラフを表示する対象を選択", graph_options)
                
                target_data = None
                target_budget_graph = 0
                graph_title_prefix = selected_graph_item
                
                # データ抽出
                if selected_graph_item == "全体合計":
                    target_data = perf_df.groupby('target_date')[['gross', 'impression', 'click']].sum().reset_index()
                    target_budget_graph = master_df['monthly_budget'].sum()
                elif selected_graph_item.startswith("【アカウント】"):
                    target_acc_name = selected_graph_item.replace("【アカウント】", "")
                    target_ids = master_df[master_df['account_name'] == target_acc_name]['campaign_id'].values
                    target_budget_graph = master_df[master_df['account_name'] == target_acc_name]['monthly_budget'].sum()
                    base_data = perf_df[perf_df['campaign_id'].isin(target_ids)].copy()
                    if not base_data.empty:
                        target_data = base_data.groupby('target_date')[['gross', 'impression', 'click']].sum().reset_index()
                else:
                    target_camp_name = selected_graph_item.replace("【キャンペーン】", "")
                    target_rows = master_df[master_df['campaign_name'] == target_camp_name]
                    if not target_rows.empty:
                        target_camp_id = target_rows.iloc[0]['campaign_id']
                        target_budget_graph = target_rows.iloc[0]['monthly_budget']
                        target_data = perf_df[perf_df['campaign_id'] == target_camp_id].copy()
                        target_data = target_data[['target_date', 'gross', 'impression', 'click']]

                # グラフ描画
                if target_data is not None and not target_data.empty:
                    target_data = target_data.sort_values('target_date')
                    target_data['cum_gross'] = target_data['gross'].cumsum()
                    target_data['cum_imp'] = target_data['impression'].cumsum()
                    target_data['cum_click'] = target_data['click'].cumsum()
                    
                    target_data['daily_ctr'] = (target_data['click'] / target_data['impression'] * 100).fillna(0)
                    target_data['cum_ctr'] = (target_data['cum_click'] / target_data['cum_imp'] * 100).fillna(0)
                    target_data['daily_cpm'] = (target_data['gross'] / target_data['impression'] * 1000).fillna(0)

                    # 残予算計算（グラフ用）
                    if target_budget_graph > 0:
                        target_data['remaining_budget'] = target_budget_graph - target_data['cum_gross']
                        target_data['actual_progress'] = (target_data['cum_gross'] / target_budget_graph) * 100
                    else:
                        target_data['remaining_budget'] = 0
                        target_data['actual_progress'] = 0

                    last_day_of_month = calendar.monthrange(start_date.year, start_date.month)[1]
                    month_dates = [datetime.date(start_date.year, start_date.month, d) for d in range(1, last_day_of_month + 1)]
                    ideal_df = pd.DataFrame({'date': month_dates})
                    ideal_df['date'] = pd.to_datetime(ideal_df['date'])
                    ideal_df['ideal_progress'] = (ideal_df.index + 1) / last_day_of_month * 100

                    daily_target_budget = target_budget_graph / last_day_of_month
                    daily_target_click = daily_target_budget / 100
                    ideal_df['ideal_cum_click'] = (ideal_df.index + 1) * daily_target_click
                    ideal_df['ideal_daily_click'] = daily_target_click

                    # 予測・挽回計算
                    latest_actual_date = target_data['target_date'].max()
                    latest_cum_gross = target_data.loc[target_data['target_date'] == latest_actual_date, 'cum_gross'].values[0]
                    latest_cum_click = target_data.loc[target_data['target_date'] == latest_actual_date, 'cum_click'].values[0]
                    days_remaining = (ideal_df['date'].max() - latest_actual_date).days
                    
                    forecast_df = pd.DataFrame() 
                    recovery_df = pd.DataFrame()

                    if days_remaining > 0:
                        future_dates = [latest_actual_date + datetime.timedelta(days=i) for i in range(1, days_remaining + 1)]
                        days_elapsed_val = (latest_actual_date.date() - start_date).days + 1
                        if days_elapsed_val < 1: days_elapsed_val = 1
                        
                        avg_daily_gross = latest_cum_gross / days_elapsed_val
                        avg_daily_click = latest_cum_click / days_elapsed_val
                        
                        forecast_values_gross = [latest_cum_gross + (avg_daily_gross * i) for i in range(1, days_remaining + 1)]
                        forecast_values_click = [latest_cum_click + (avg_daily_click * i) for i in range(1, days_remaining + 1)]
                        
                        forecast_df = pd.DataFrame({
                            'date': future_dates,
                            'forecast_cum_gross': forecast_values_gross,
                            'forecast_cum_click': forecast_values_click
                        })
                        if target_budget_graph > 0:
                            forecast_df['forecast_progress'] = (forecast_df['forecast_cum_gross'] / target_budget_graph) * 100
                        else:
                            forecast_df['forecast_progress'] = 0

                        remaining_budget = target_budget_graph - latest_cum_gross
                        if remaining_budget < 0: remaining_budget = 0
                        req_daily_gross = remaining_budget / days_remaining
                        req_daily_click = req_daily_gross / 100
                        
                        recovery_df = pd.DataFrame({
                            'date': future_dates,
                            'req_daily_click': [req_daily_click] * days_remaining,
                            'recovery_progress': [0] * days_remaining # dummy
                        })
                        # 挽回進捗は計算省略(使わないため)
                        if target_budget_graph > 0:
                             # グラフ描画に必要な列だけ計算
                             recovery_cum_gross = [latest_cum_gross + (req_daily_gross * i) for i in range(1, days_remaining + 1)]
                             recovery_df['recovery_progress'] = [(val / target_budget_graph * 100) for val in recovery_cum_gross]
                             recovery_cum_click = [latest_cum_click + (req_daily_click * i) for i in range(1, days_remaining + 1)]
                             recovery_df['recovery_cum_click'] = recovery_cum_click


                    # --------------------------------------------------------
                    # グラフ1：進捗・ボリューム分析
                    # --------------------------------------------------------
                    st.subheader("① 予算・ボリューム分析（進捗 & Click）")
                    fig1 = make_subplots(
                        rows=3, cols=1, 
                        shared_xaxes=True, 
                        vertical_spacing=0.08,
                        subplot_titles=(f"進捗率の推移", f"累積Click推移", f"日別Click推移"),
                        specs=[[{"secondary_y": False}], [{"secondary_y": True}], [{"secondary_y": True}]]
                    )
                    fig1.add_trace(go.Scatter(x=ideal_df['date'], y=ideal_df['ideal_progress'], mode='lines', name='理想線', line=dict(color='lightgray', dash='dot')), row=1, col=1)
                    fig1.add_trace(go.Scatter(x=target_data['target_date'], y=target_data['actual_progress'], mode='lines+markers', name='実績', line=dict(color='red', width=3)), row=1, col=1)
                    if not forecast_df.empty:
                        fig1.add_trace(go.Scatter(x=forecast_df['date'], y=forecast_df['forecast_progress'], mode='lines', name='予測(現状維持)', line=dict(color='green', dash='dot')), row=1, col=1)
                    if not recovery_df.empty:
                        fig1.add_trace(go.Scatter(x=recovery_df['date'], y=recovery_df['recovery_progress'], mode='lines', name='必要ペース', line=dict(color='deeppink', dash='dot')), row=1, col=1)

                    fig1.add_trace(go.Scatter(x=ideal_df['date'], y=ideal_df['ideal_cum_click'], name='理想累積(CPC100円)', mode='lines', line=dict(color='lightgray', dash='dot')), row=2, col=1, secondary_y=True)
                    fig1.add_trace(go.Scatter(x=target_data['target_date'], y=target_data['cum_click'], name='実績累積Click', mode='lines+markers', line=dict(color='orange', width=2)), row=2, col=1, secondary_y=True)
                    if not forecast_df.empty:
                        fig1.add_trace(go.Scatter(x=forecast_df['date'], y=forecast_df['forecast_cum_click'], name='予測累積Click', mode='lines', line=dict(color='green', dash='dot')), row=2, col=1, secondary_y=True)
                    if not recovery_df.empty:
                        fig1.add_trace(go.Scatter(x=recovery_df['date'], y=recovery_df['recovery_cum_click'], name='必要累積Click', mode='lines', line=dict(color='deeppink', dash='dot')), row=2, col=1, secondary_y=True)
                    fig1.add_trace(go.Bar(x=target_data['target_date'], y=target_data['cum_imp'], name='実績累積IMP', opacity=0.1, marker_color='gray'), row=2, col=1, secondary_y=False)

                    fig1.add_trace(go.Scatter(x=target_data['target_date'], y=target_data['click'], name='日別Click', mode='lines+markers', line=dict(color='navy', width=2)), row=3, col=1, secondary_y=True)
                    fig1.add_trace(go.Scatter(x=ideal_df['date'], y=ideal_df['ideal_daily_click'], name='理想日別(CPC100円)', mode='lines', line=dict(color='lightgray', dash='dot')), row=3, col=1, secondary_y=True)
                    if not recovery_df.empty:
                        fig1.add_trace(go.Scatter(x=recovery_df['date'], y=recovery_df['req_daily_click'], name='明日からの必要数', mode='lines', line=dict(color='deeppink', dash='dot', width=2)), row=3, col=1, secondary_y=True)
                    fig1.add_trace(go.Bar(x=target_data['target_date'], y=target_data['impression'], name='日別IMP', opacity=0.4, marker_color='lightblue'), row=3, col=1, secondary_y=False)

                    fig1.update_layout(height=900, showlegend=True, hovermode="x unified")
                    fig1.update_yaxes(title_text="進捗率 (%)", range=[0, 110], row=1, col=1)
                    fig1.update_yaxes(title_text="累積IMP", row=2, col=1, secondary_y=False)
                    fig1.update_yaxes(title_text="累積Click", row=2, col=1, secondary_y=True)
                    fig1.update_yaxes(title_text="日別IMP", row=3, col=1, secondary_y=False)
                    fig1.update_yaxes(title_text="日別Click", row=3, col=1, secondary_y=True)
                    st.plotly_chart(fig1, use_container_width=True)

                    # --------------------------------------------------------
                    # グラフ2：効率・品質分析
                    # --------------------------------------------------------
                    st.subheader("② 効率・品質分析（CTR & CPM）")
                    fig2 = make_subplots(
                        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=(f"CTR(クリック率)推移", f"コスト効率分析 [CPM vs CTR]"),
                        specs=[[{"secondary_y": False}], [{"secondary_y": True}]]
                    )
                    fig2.add_trace(go.Scatter(x=target_data['target_date'], y=target_data['daily_ctr'], name='日別CTR', mode='lines+markers', line=dict(color='blue', width=2)), row=1, col=1)
                    fig2.add_trace(go.Scatter(x=target_data['target_date'], y=target_data['cum_ctr'], name='累計CTR', mode='lines', line=dict(color='orange', dash='dot', width=2)), row=1, col=1)
                    
                    fig2.add_trace(go.Bar(x=target_data['target_date'], y=target_data['daily_cpm'], name='日別CPM', opacity=0.6, marker_color='purple'), row=2, col=1, secondary_y=False)
                    fig2.add_trace(go.Scatter(x=target_data['target_date'], y=target_data['daily_ctr'], name='日別CTR', mode='lines+markers', line=dict(color='blue', width=2)), row=2, col=1, secondary_y=True)
                    
                    fig2.update_layout(height=700, showlegend=True, hovermode="x unified")
                    fig2.update_yaxes(title_text="CTR (%)", row=1, col=1)
                    fig2.update_yaxes(title_text="CPM (円)", row=2, col=1, secondary_y=False)
                    fig2.update_yaxes(title_text="CTR (%)", row=2, col=1, secondary_y=True)
                    st.plotly_chart(fig2, use_container_width=True)

                    # --------------------------------------------------------
                    # ★新規グラフ3：予算管理分析（Gross & Budget）
                    # --------------------------------------------------------
                    st.subheader("③ 予算管理分析（Gross & Budget）")
                    fig3 = make_subplots(
                        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=(f"累積消化額 vs 残予算の推移", f"日別消化額の推移"),
                        specs=[[{"secondary_y": True}], [{"secondary_y": False}]]
                    )

                    # 上段: 累積消化(面) vs 残予算(線)
                    fig3.add_trace(go.Scatter(x=target_data['target_date'], y=target_data['cum_gross'], name='累積消化額', mode='lines', fill='tozeroy', line=dict(color='royalblue')), row=1, col=1, secondary_y=False)
                    fig3.add_trace(go.Scatter(x=target_data['target_date'], y=target_data['remaining_budget'], name='残予算', mode='lines', line=dict(color='mediumseagreen', width=3)), row=1, col=1, secondary_y=True)
                    # 予算上限ライン
                    fig3.add_trace(go.Scatter(x=[target_data['target_date'].min(), target_data['target_date'].max()], y=[target_budget_graph, target_budget_graph], name='予算上限', mode='lines', line=dict(color='red', dash='dot')), row=1, col=1, secondary_y=False)

                    # 下段: 日別消化
                    fig3.add_trace(go.Bar(x=target_data['target_date'], y=target_data['gross'], name='日別消化額', marker_color='royalblue'), row=2, col=1)
                    # 日割り目安
                    fig3.add_trace(go.Scatter(x=ideal_df['date'], y=[daily_target_budget]*len(ideal_df), name='日割り目安', mode='lines', line=dict(color='gray', dash='dot')), row=2, col=1)

                    fig3.update_layout(height=700, showlegend=True, hovermode="x unified")
                    fig3.update_yaxes(title_text="累積消化額 (円)", row=1, col=1, secondary_y=False)
                    fig3.update_yaxes(title_text="残予算 (円)", row=1, col=1, secondary_y=True)
                    fig3.update_yaxes(title_text="日別消化額 (円)", row=2, col=1)
                    st.plotly_chart(fig3, use_container_width=True)

                else:
                    st.info("📊 グラフを表示するためのデータがありません。")
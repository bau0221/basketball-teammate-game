# basketball_teammate_game.py
# 使用 Streamlit 打造一個「共同隊友猜猜看」互動遊戲介面
# 安裝：pip install streamlit requests beautifulsoup4 pandas lxml
# 執行：streamlit run basketball_teammate_game.py

import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import urllib.parse
import random
import time
from io import StringIO

# 設置頁面配置
st.set_page_config(
    page_title="共同隊友猜猜看",
    page_icon="🏀",
    layout="wide"
)

# 快取搜尋結果
@st.cache_data(ttl=3600)  # 1小時過期
def search_player(player_name: str):
    """搜索球員"""
    try:
        search_url = "https://www.basketball-reference.com/search/search.fcgi"
        params = {'search': player_name}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        resp = requests.get(search_url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')

        results = []
        
        # 檢查是否直接重定向到球員頁面
        if '/players/' in resp.url:
            # 直接重定向到球員頁面
            pid = resp.url.split('/')[-1].replace('.html', '')
            # 從頁面標題獲取球員名字
            title = soup.find('title')
            if title:
                name = title.get_text().split(' Stats')[0]
                results.append({'name': name, 'pid': pid, 'url': resp.url})
        else:
            # 搜索結果頁面
            search_results = soup.find('div', {'class': 'search-results'})
            if search_results:
                for link in search_results.find_all('a'):
                    href = link.get('href', '')
                    if '/players/' in href:
                        pid = href.split('/')[-1].replace('.html', '')
                        name = link.get_text(strip=True)
                        url = urllib.parse.urljoin("https://www.basketball-reference.com", href)
                        results.append({'name': name, 'pid': pid, 'url': url})
        
        return results
    except Exception as e:
        st.error(f"搜索球員時發生錯誤: {str(e)}")
        return []

# 快取隊友清單
@st.cache_data(ttl=3600)  # 1小時過期
def fetch_teammates(pid: str, full_name: str):
    """獲取球員隊友列表"""
    try:
        base_url = "https://www.basketball-reference.com/friv/teammates_and_opponents.fcgi"
        params = {
            'pid_select': full_name,  # 關鍵：使用 full_name 而不是 pid
            'pid': pid,
            'idx': 'players',
            'type': 't'
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'lxml')
        table = soup.find('table')
        
        if table is None:
            st.warning(f"找不到 {full_name} 的隊友表格")
            return []
        
        # 使用你的方法：直接用 pandas.read_html 配合 StringIO
        from io import StringIO
        df = pd.read_html(StringIO(str(table)))[0]
        
        # 找到 Teammate 欄位
        teammates = []
        
        # 處理多層表頭
        if hasattr(df.columns, 'nlevels') and df.columns.nlevels > 1:
            # 找到包含 "Teammate" 的欄位
            for col in df.columns:
                if isinstance(col, tuple):
                    if any('Teammate' in str(x) for x in col):
                        teammates_series = df[col]
                        break
                elif 'Teammate' in str(col):
                    teammates_series = df[col]
                    break
        else:
            # 單層表頭
            if 'Teammate' in df.columns:
                teammates_series = df['Teammate']
            elif len(df.columns) > 1:
                # 假設第二欄是隊友名稱
                teammates_series = df.iloc[:, 1]
            else:
                return []
        
        # 清理數據
        if 'teammates_series' in locals():
            teammates = teammates_series.dropna().astype(str).tolist()
            # 移除星號和其他符號
            teammates = [t.replace('*', '').strip() for t in teammates if t and t != 'nan']
            # 過濾掉無效項目
            teammates = [t for t in teammates if len(t) > 2 and not t.isdigit()]
        
        return teammates
            
    except Exception as e:
        st.error(f"獲取 {full_name} 隊友資料時發生錯誤: {str(e)}")
        return []

def reset_game():
    """重置遊戲狀態"""
    keys_to_remove = ['answer', 'common', 'selected_players', 'game_started', 'search_completed', 'choices1', 'choices2', 'choices3']
    for key in keys_to_remove:
        if key in st.session_state:
            del st.session_state[key]

# 初始化session state
if 'game_started' not in st.session_state:
    st.session_state['game_started'] = False

# 標題與說明
st.title("🏀 共同隊友猜猜看")
st.markdown("""
### 遊戲規則：
1. 輸入三位 NBA 球員的名字
2. 程式會找出曾與這三位球員都同隊過的球員
3. 隨機選擇一位作為答案，讓你來猜猜看！

---
""")

# 創建兩列布局
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("輸入球員名字")
    
    # 三位球員輸入
    p1 = st.text_input("第一位球員：", placeholder="例如：LeBron James")
    p2 = st.text_input("第二位球員：", placeholder="例如：Kyrie Irving")
    p3 = st.text_input("第三位球員：", placeholder="例如：Kevin Love")

with col2:
    st.subheader("遊戲控制")
    start_game = st.button("🎮 開始遊戲", type="primary")
    reset_button = st.button("🔄 重新開始")
    
    if reset_button:
        reset_game()
        st.rerun()

# 開始遊戲邏輯
if start_game:
    if not p1 or not p2 or not p3:
        st.warning("⚠️ 請輸入三位球員的名字。")
    else:
        with st.spinner("正在搜索球員資料..."):
            # 搜尋候選
            choices1 = search_player(p1)
            choices2 = search_player(p2)
            choices3 = search_player(p3)
            
        # 錯誤處理
        if not choices1:
            st.error(f"❌ 找不到球員：{p1}")
        elif not choices2:
            st.error(f"❌ 找不到球員：{p2}")
        elif not choices3:
            st.error(f"❌ 找不到球員：{p3}")
        else:
            # 將搜索結果保存到session state
            st.session_state['choices1'] = choices1
            st.session_state['choices2'] = choices2
            st.session_state['choices3'] = choices3
            st.session_state['search_completed'] = True
            st.success("✅ 成功找到所有球員！")

# 顯示球員選擇（當搜索完成後）
if st.session_state.get('search_completed'):
    # 球員選擇函數
    def select_player(choices, label, key):
        if len(choices) == 1:
            st.info(f"{label}: {choices[0]['name']}")
            return choices[0]
        else:
            options = {f"{c['name']} ({c['pid']})": c for c in choices}
            sel_key = st.selectbox(
                f"請選擇 {label}：", 
                list(options.keys()),
                key=key
            )
            return options[sel_key]

    # 顯示球員選擇
    st.subheader("確認球員選擇")
    sel1 = select_player(st.session_state['choices1'], "第一位球員", "sel1")
    sel2 = select_player(st.session_state['choices2'], "第二位球員", "sel2")
    sel3 = select_player(st.session_state['choices3'], "第三位球員", "sel3")

    if st.button("確認選擇並開始查找共同隊友", key="confirm_players"):
        with st.spinner("正在分析隊友關係..."):
            # 取得隊友清單 - 注意：現在需要傳入 full_name
            t1 = fetch_teammates(sel1['pid'], sel1['name'])
            t2 = fetch_teammates(sel2['pid'], sel2['name'])
            t3 = fetch_teammates(sel3['pid'], sel3['name'])
            
            st.write(f"- {sel1['name']} 的隊友數量: {len(t1)}")
            st.write(f"- {sel2['name']} 的隊友數量: {len(t2)}")
            st.write(f"- {sel3['name']} 的隊友數量: {len(t3)}")
            
            # 顯示前幾個隊友作為調試信息
            if t1:
                st.write(f"  前5個隊友: {t1[:5]}")
            if t2:
                st.write(f"  前5個隊友: {t2[:5]}")
            if t3:
                st.write(f"  前5個隊友: {t3[:5]}")
            
            # 計算交集
            common = set(t1) & set(t2) & set(t3)

            if not common:
                st.warning("😔 這三位球員沒有共同隊友，請重新選擇其他球員。")
                # 顯示兩兩交集來幫助調試
                st.write(f"- {sel1['name']} 和 {sel2['name']} 的共同隊友: {len(set(t1) & set(t2))} 個")
                st.write(f"- {sel1['name']} 和 {sel3['name']} 的共同隊友: {len(set(t1) & set(t3))} 個")
                st.write(f"- {sel2['name']} 和 {sel3['name']} 的共同隊友: {len(set(t2) & set(t3))} 個")
            else:
                answer = random.choice(list(common))
                # 將答案與候選存入 session
                st.session_state['answer'] = answer
                st.session_state['common'] = list(common)
                st.session_state['selected_players'] = [sel1['name'], sel2['name'], sel3['name']]
                st.session_state['game_started'] = True
                
                st.success(f"🎯 找到 {len(common)} 位共同隊友！我已經選好了一位，請開始猜測！")
                st.balloons()
                # 強制重新運行以顯示猜測區域
                st.rerun()

# 顯示猜測區域
if st.session_state.get('game_started') and 'answer' in st.session_state:
    st.markdown("---")
    st.subheader("🤔 開始猜測")
    
    # 顯示選定的球員
    col1, col2, col3 = st.columns(3)
    players = st.session_state.get('selected_players', [])
    if len(players) >= 3:
        with col1:
            st.info(f"球員 1: {players[0]}")
        with col2:
            st.info(f"球員 2: {players[1]}")
        with col3:
            st.info(f"球員 3: {players[2]}")
    
    st.write(f"💡 提示：共有 {len(st.session_state['common'])} 位可能的答案")
    
    guess = st.text_input("請猜這位共同隊友的名字：", key="guess_input", placeholder="輸入球員姓名...")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        submit_guess = st.button("✅ 提交答案", type="primary")
    with col2:
        show_hint = st.button("💡 顯示提示")
    
    if show_hint:
        st.info(f"提示：答案的第一個字母是 '{st.session_state['answer'][0]}'")
    
    if submit_guess and guess:
        if guess.strip().lower() == st.session_state['answer'].strip().lower():
            st.balloons()
            st.success(f"🎉 恭喜！猜對了，答案就是 **{st.session_state['answer']}**！")
            
            with st.expander("🔍 查看所有可能的共同隊友"):
                common_sorted = sorted(st.session_state['common'])
                for i, teammate in enumerate(common_sorted, 1):
                    st.write(f"{i}. {teammate}")
                    
        else:
            st.error("❌ 猜錯囉，再試試看！")
            
            # 檢查是否接近正確答案
            if guess.strip().lower() in [t.lower() for t in st.session_state['common']]:
                st.warning("🔥 很接近了！這個球員確實是共同隊友，但不是我選的答案。")

# 側邊欄資訊
with st.sidebar:
    st.header("ℹ️ 遊戲資訊")
    st.write("這個遊戲使用 Basketball Reference 網站的資料來查找球員的隊友關係。")
    
    if st.session_state.get('game_started'):
        st.write("### 🎮 當前遊戲狀態")
        st.write("遊戲進行中...")
        if 'answer' in st.session_state:
            st.write(f"共同隊友數量: {len(st.session_state['common'])}")
    
    st.write("### 📝 使用說明")
    st.write("1. 輸入三位NBA球員姓名")
    st.write("2. 確認球員選擇")
    st.write("3. 猜測共同隊友")
    st.write("4. 查看結果")
    
    st.write("### ⚠️ 注意事項")
    st.write("- 需要網路連接")
    st.write("- 查詢可能需要一些時間")
    st.write("- 請使用英文球員姓名")
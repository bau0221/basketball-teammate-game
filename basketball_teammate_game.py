# basketball_teammate_game.py
# 使用 Streamlit 打造一個「共同隊友猜猜看」互動遊戲介面
# 安裝：pip install streamlit requests beautifulsoup4 pandas lxml unicodedata
# 執行：streamlit run basketball_teammate_game.py

import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import urllib.parse
import random
import time
from io import StringIO
import unicodedata
from nba_api.stats.static import players as nba_players

# 設置頁面配置
st.set_page_config(
    page_title="共同隊友猜猜看",
    page_icon="🏀",
    layout="wide"
)


@st.cache_data(ttl=86400, show_spinner="下載球員名單中…")
def fetch_all_players() -> list[str]:
    """回傳去重、排序後的 NBA 全名清單（~3,000 筆）。"""
    all_players = nba_players.get_players()
# 只取 is_active == True 的球員
    active_players = [p for p in all_players if p['is_active']]
    # 如果只要名字列表：
    active_names = [p['full_name'] for p in active_players]
    return sorted(active_names)


def generate_computer_question(max_trials: int = 20, min_games: int = 20) -> dict | None:
    """
    1. 隨機選一位球員作為保底答案
    2. 從他的隊友中隨機選3位作為線索
    3. 用這3位線索去跑共同隊友邏輯
    4. 結果一定包含原球員，可能包含其他答案
    """
    all_players = fetch_all_players()
    rng = random.Random(time.time())
    trials = 0
    
    while trials < max_trials:
        trials += 1
        
        # 步驟1: 隨機選一位球員作為保底答案
        target_player = rng.choice(all_players)
        
        try:
            # 搜索這位目標球員
            search_result = search_player(target_player)
            if not search_result:
                continue
            
            target_info = search_result[0]
            
            # 步驟2: 獲取目標球員的隊友，並隨機選3位作為線索
            target_teammates = fetch_teammates(target_info['pid'], target_info['name'], min_games=min_games)
            
            if len(target_teammates) < 3:
                continue  # 隊友不足3位，跳過
            
            # 隨機選3位隊友作為線索
            clue_players = rng.sample(target_teammates, 3)
            
            # 步驟3: 搜索這3位線索球員
            clue_search_results = []
            for clue_player in clue_players:
                result = search_player(clue_player)
                if not result:
                    break  # 如果任一線索球員搜不到就跳過這組
                clue_search_results.append(result[0])
            
            if len(clue_search_results) != 3:
                continue
            
            # 步驟4: 獲取3位線索球員的隊友清單
            clue_teammates_lists = []
            for result in clue_search_results:
                teammates = fetch_teammates(result['pid'], result['name'], min_games=min_games)
                if not teammates:
                    break
                clue_teammates_lists.append(teammates)
            
            if len(clue_teammates_lists) != 3:
                continue
            
            # 步驟5: 計算交集（共同隊友）
            common = set(clue_teammates_lists[0]) & set(clue_teammates_lists[1]) & set(clue_teammates_lists[2])
            common = {c for c in common if c.lower() != 'teammate'}  # 過濾掉無效項目
            
            # 驗證：目標球員應該在共同隊友中（因為他跟3位線索都當過隊友）
            target_normalized = normalize_name(target_player)
            common_normalized = [normalize_name(c) for c in common]
            
            if target_normalized not in common_normalized:
                # 理論上不應該發生，但如果發生就手動加入
                common.add(target_player)
            
            # 檢查共同隊友數量是否合適
            if len(common) >= 1:  # 至少有目標球員本人
                return {
                    "clues": [result['name'] for result in clue_search_results],  # 三位線索球員
                    "all_answers": list(common),  # 所有共同隊友作為可能答案
                    "guaranteed_answer": target_player,  # 保底答案
                    "answer": target_player  # 用保底答案作為提示答案
                }
                
        except Exception as e:
            # 如果這組球員處理出錯就繼續下一組
            continue
    
    return None


# 快取搜尋結果
@st.cache_data(ttl=3600)  # 1小時過期
def search_player(player_name: str):
    time.sleep(3) 
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
@st.cache_data(ttl=3600)        # 1 小時快取
def fetch_teammates(pid: str,
                    full_name: str,
                    min_games: int = 0   # ⇦ 新增：設定門檻，傳 50 就會只挑 G>50
                   ) -> list[str]:
    """
    讀取 Basketball-Reference 的「Teammates & Opponents」表格，
    回傳符合條件 (G > min_games) 的隊友姓名清單。
    """
    try:
        # 1. 下載表格 ----------------------------------------------------------
        base_url = "https://www.basketball-reference.com/friv/teammates_and_opponents.fcgi"
        params   = {
            "pid_select": full_name,     # 用 full name
            "pid":        pid,
            "idx":        "players",
            "type":       "t"
        }
        headers  = {"User-Agent": "Mozilla/5.0"}

        url  = f"{base_url}?{urllib.parse.urlencode(params)}"
        html = requests.get(url, headers=headers, timeout=15)
        html.raise_for_status()

        table = BeautifulSoup(html.text, "lxml").find("table")
        if table is None:
            st.warning(f"找不到 {full_name} 的隊友表格")
            return []

        df = pd.read_html(StringIO(str(table)))[0]

        # 2. 找出「Teammate」欄與「G」欄 -------------------------------------
        # teammate_col：可能是 'Teammate' 或多層 header 中含 'Teammate'
        teammate_col = next(
            (col for col in df.columns                 # 產生器
            if 'Teammate' in (col if isinstance(col, str)
                            else ' '.join(map(str, col)))),
            None                                        # ⇦ 預設值
        )

        # g_col：欄名恰為 'G' 或多層 header 最末層為 'G'
        g_col = next(
            (col for col in df.columns
             if (isinstance(col, str) and col.strip() == "G")
             or (isinstance(col, tuple) and col[-1].strip() == "G"))
        , None)

        if teammate_col is None:
            return []     # 意外：抓不到隊友欄
        if g_col is None:
            g_mask = pd.Series([True] * len(df))   # 找不到 G 欄就不過濾
        else:
            g_mask = pd.to_numeric(df[g_col], errors="coerce").gt(min_games)

        # 3. 過濾並清理 -------------------------------------------------------
        teammates = (
            df.loc[g_mask, teammate_col]       # 只留 G > min_games 的列
              .dropna()
              .astype(str)
              .str.replace(r"\*", "", regex=True)   # 去掉星號 (現役標記)
              .str.strip()
              .loc[lambda s: (s.str.len() > 2) & (~s.str.isdigit())]
              .tolist()
        )

        return teammates

    except Exception as e:
        st.error(f"獲取 {full_name} 隊友資料時發生錯誤: {e}")
        return []

def reset_game():
    """重置遊戲狀態"""
    keys_to_remove = ['answer', 'common', 'selected_players', 'game_started', 'search_completed', 'choices1', 'choices2', 'choices3']
    for key in keys_to_remove:
        if key in st.session_state:
            del st.session_state[key]


def normalize_name(name: str) -> str:
    """
    去除重音符號、轉小寫並去除前後空白
    例如 "Nurkić" → "nurkic"
    """
    nfkd = unicodedata.normalize('NFKD', name)
    no_marks = ''.join(ch for ch in nfkd if not unicodedata.combining(ch))
    # **重點：轉小寫**，確保大小寫無關
    return no_marks.lower().strip()
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
with st.sidebar:
    mode = st.radio("🎮 遊戲模式", ["玩家模式", "電腦模式"], index=0, key="game_mode")
# 創建兩列布局
# ----- 玩家模式 -------------------------------------------------
if mode == "玩家模式":
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("輸入球員名字")
        p1 = st.text_input("第一位球員：", placeholder="例如：LeBron James")
        p2 = st.text_input("第二位球員：", placeholder="例如：Kyrie Irving")
        p3 = st.text_input("第三位球員：", placeholder="例如：Kevin Love")

    with col2:
        st.subheader("遊戲控制")
        start_game   = st.button("🎮 開始遊戲", type="primary")
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
                common = {c for c in common if c.lower() != 'teammate'}
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
                    
                    st.success(f"🎯 找到 {len(common)} 位共同隊友！請開始猜測！")
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
        
        # 三個按鈕：提交／提示／放棄
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            submit_guess = st.button("✅ 提交答案", type="primary")
        with col2:
            show_hint   = st.button("💡 顯示提示")
        with col3:
            give_up     = st.button("🛑 放棄並顯示答案")

        if show_hint:
            st.info(f"提示：答案的第一個字母是 '{st.session_state['answer'][0]}'")
        
        # 在猜測判斷時這樣寫
        if submit_guess and guess:
            # 正規化
            user_guess = normalize_name(guess)
            # 全部共同隊友正規化列表
            common_norm = [normalize_name(t) for t in st.session_state['common']]

            if user_guess in common_norm:
                # 猜到任一位共同隊友都算成功
                st.balloons()
                st.success(f"🎉 恭喜你！**{guess.strip()}** 也是這三位球員的共同隊友！")
                with st.expander("🔍 查看所有可能的共同隊友"):
                    for i, teammate in enumerate(sorted(st.session_state['common']), 1):
                        st.write(f"{i}. {teammate}")
            else:
                st.error("❌ 猜錯囉，再試試看！")

        if give_up:
            st.error(f"🤷‍♂️ 放棄啦，隨機答案是 **{st.session_state['answer']}**！")
            # 顯示所有可能答案
            with st.expander("🔍 查看所有可能的共同隊友"):
                for i, teammate in enumerate(sorted(st.session_state['common']), 1):
                    st.write(f"{i}. {teammate}")

# --- 新增／修改開始：電腦模式主要區塊 ------------------------------------
# 電腦模式主要區塊
if mode == "電腦模式":
    st.title("🏀 電腦出題：猜猜我是誰？")
    
    # 難易度選擇
    difficulty = st.radio(
        "🎚️  選擇難易度",
        ("簡單(大概率同隊)", "困難"),
        horizontal=True,
        key="diff_level"
    )
    min_games = 50 if difficulty == "簡單" else 0
    
    if st.button("🎲 電腦出題", key="start_computer_game", type="primary"):
        with st.spinner("正在生成題目，請稍候..."):
            q = generate_computer_question(min_games=min_games)
        
        if q is None:
            st.error("目前抓不到合適題目，請稍後再試。")
        else:
            st.session_state["comp_question"] = q
            st.session_state["comp_start"] = True
            answer_count = len(q["all_answers"])
            if answer_count == 1:
                st.success(f"題目已產生！這組線索只有 1 個答案，請開始猜測👇")
            else:
                st.success(f"題目已產生！這組線索有 {answer_count} 個可能答案，請開始猜測👇")
    
    # 顯示題目
    if st.session_state.get("comp_start"):
        q = st.session_state["comp_question"]
        
        st.markdown("---")
        st.subheader("🤔 開始猜測")
        
        # 顯示三位線索球員
        st.write("🔍 **線索：以下三位球員的共同隊友**")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info(f"球員 1: {q['clues'][0]}")
        with col2:
            st.info(f"球員 2: {q['clues'][1]}")
        with col3:
            st.info(f"球員 3: {q['clues'][2]}")
        
        # 顯示可能答案數量提示
        answer_count = len(q["all_answers"])
        if answer_count == 1:
            st.write("💡 提示：這組線索只有唯一答案")
        else:
            st.write(f"💡 提示：共有 {answer_count} 位可能的答案")
        
        guess = st.text_input("請猜這位共同隊友的名字：", key="comp_guess", placeholder="輸入球員姓名...")
        
        # 三個按鈕
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            submit_guess = st.button("✅ 提交答案", type="primary")
        with col2:
            show_hint = st.button("💡 顯示提示")
        with col3:
            give_up = st.button("🛑 放棄並顯示答案")
        
        if show_hint:
            st.info(f"提示：保底答案的第一個字母是 '{q['guaranteed_answer'][0]}'")
        
        if submit_guess and guess:
            # 正規化用戶輸入
            user_guess = normalize_name(guess)
            # 正規化所有可能答案
            answers_norm = [normalize_name(ans) for ans in q["all_answers"]]
            
            if user_guess in answers_norm:
                # 找出用戶猜中的原始答案名稱
                matched_answer = next(
                    ans for ans in q["all_answers"] 
                    if normalize_name(ans) == user_guess
                )
                
                st.balloons()
                st.success(f"🎉 恭喜你！**{matched_answer}** 確實是這三位球員的共同隊友！")
                
                # 顯示所有可能答案
                if len(q["all_answers"]) > 1:
                    with st.expander("🔍 查看所有可能的共同隊友"):
                        for i, teammate in enumerate(sorted(q["all_answers"]), 1):
                            if normalize_name(teammate) == user_guess:
                                st.write(f"{i}. **{teammate}** ← 你的答案")
                            else:
                                st.write(f"{i}. {teammate}")
                
                st.session_state["comp_start"] = False
            else:
                st.error("❌ 猜錯囉，再試試看！")
        
        if give_up:
            if len(q["all_answers"]) == 1:
                st.error(f"🤷‍♂️ 答案是：**{q['all_answers'][0]}**")
            else:
                st.error(f"🤷‍♂️ 所有可能的答案如下：")
                for i, teammate in enumerate(sorted(q["all_answers"]), 1):
                    if teammate == q['guaranteed_answer']:
                        st.write(f"{i}. **{teammate}** ← 保底答案")
                    else:
                        st.write(f"{i}. {teammate}")
            
            st.session_state["comp_start"] = False
# --- 新增／修改結束 -------------------------------------------------------



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

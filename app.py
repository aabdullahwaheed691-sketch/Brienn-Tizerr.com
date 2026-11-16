import streamlit as st
import google.generativeai as genai
import io
import time
import re
import os
import json
from datetime import datetime

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from supabase import create_client

# ---------------------------------------------------------
# 1. PAGE CONFIGURATION & CUSTOM STYLING
# ---------------------------------------------------------
st.set_page_config(
    page_title="Brienn Tizerr.pk v1.7",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.stApp { background-color: #0E1117; color: #FFFFFF; }
h1, h2, h3, .green-header { color: #00FF66 !important; }
p, label, span, div, .stMarkdown { color: #FFFFFF !important; }
.stTextInput > div > div > input, .stSelectbox > div > div {
    background-color: #1E222A !important; color: #FFFFFF !important; border: 1px solid #00FF66 !important;
}
.stButton > button {
    background-color: #00FF66 !important; color: #0E1117 !important; font-weight: bold !important; border-radius: 5px !important;
}
.sub-banner {
    border: 2px solid #00FF66; background-color: #1A231F; padding: 20px; border-radius: 10px; margin-bottom: 25px;
}
.banned-banner {
    border: 2px solid #FF4B4B; background-color: #2B1316; padding: 20px; border-radius: 10px; margin-bottom: 25px;
}
.jazzcash-box {
    border: 1px solid #FF4B4B; background-color: #261619; padding: 15px; border-radius: 8px; margin-bottom: 15px;
}
.help-card {
    border: 1px solid #2E3440; background-color: #161B22; padding: 18px; border-radius: 8px; margin-bottom: 15px;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. SUPABASE & STREAMLIT NATIVE AUTHENTICATION SETUP
# ---------------------------------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

JAZZCASH_NUMBER = "03077045376"
JAZZCASH_TITLE = "Sheikh Abdul Majeed"
THIRTY_DAYS_SECONDS = 30 * 24 * 60 * 60

# --- STREAMLIT BUILT-IN AUTH GATE ---
if not st.user.is_logged_in:
    st.markdown("<h1 style='text-align: center; color: #00FF66;'>⚡ Welcome to Brienn Tizerr.pk</h1>",
                unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align: center;'>Please sign in with your Google account to access the PCTB Test Generator.</p>",
        unsafe_allow_html=True)

    col_auth1, col_auth2, col_auth3 = st.columns([1, 2, 1])
    with col_auth2:
        if st.button("🔐 Sign in with Google", use_container_width=True):
            st.login()
    st.stop()

# Ensure email verification check
if not getattr(st.user, "email_verified", True):
    st.error("Your Google email is not verified. Please verify it and sign in again.")
    if st.button("Sign Out"):
        st.logout()
    st.stop()

user_email = st.user.email
user_name = st.user.get("name") or "User"

# Default session states & Daily Token Reset Check
today_str = datetime.now().strftime("%Y-%m-%d")

if "token_reset_date" not in st.session_state:
    st.session_state["token_reset_date"] = today_str
elif st.session_state["token_reset_date"] != today_str:
    st.session_state["total_tokens_used"] = 0
    st.session_state["token_reset_date"] = today_str

if "last_generation_time" not in st.session_state:
    st.session_state["last_generation_time"] = None
if "provisional_tests_remaining" not in st.session_state:
    st.session_state["provisional_tests_remaining"] = 0
if "daily_total_tests" not in st.session_state:
    st.session_state["daily_total_tests"] = {}
if "admin_passkey" not in st.session_state:
    st.session_state["admin_passkey"] = "admin123"
if "show_quota_help_inline" not in st.session_state:
    st.session_state["show_quota_help_inline"] = False
if "total_tokens_used" not in st.session_state:
    st.session_state["total_tokens_used"] = 0
if "last_prompt_tokens" not in st.session_state:
    st.session_state["last_prompt_tokens"] = 0
if "last_completion_tokens" not in st.session_state:
    st.session_state["last_completion_tokens"] = 0
if "last_test_tokens" not in st.session_state:
    st.session_state["last_test_tokens"] = 0
if "editable_test_text" not in st.session_state:
    st.session_state["editable_test_text"] = ""


# --- FETCH OR INIT USER IN SUPABASE ---
def get_or_create_supabase_user(email):
    res = supabase.table("users").select("*").eq("email", email).execute()
    if res.data:
        return res.data[0]
    else:
        new_user = {
            "id": f"u_{int(time.time())}",
            "email": email,
            "phone": "0300-9876543",
            "role": "Member",
            "subscribed_at": 0,
            "provisional_claimed": False,
            "rejection_count": 0,
            "is_banned": False,
            "is_deleted": False
        }
        supabase.table("users").insert(new_user).execute()
        return new_user


current_user_record = get_or_create_supabase_user(user_email)

# Sync local session state from Supabase record
user_role = current_user_record["role"]
user_is_banned = current_user_record["is_banned"]

# --- 30-DAY AUTO-EXPIRE CHECK ---
if user_role == "Subscribed" and current_user_record["subscribed_at"] > 0:
    if (time.time() - current_user_record["subscribed_at"]) > THIRTY_DAYS_SECONDS:
        supabase.table("users").update({"role": "Member", "subscribed_at": 0}).eq("email", user_email).execute()
        user_role = "Member"

# ---------------------------------------------------------
# 3. API CONFIGURATION & MATH / RTL FORMATTING
# ---------------------------------------------------------
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])


def clean_latex_formatting(text):
    if not text or text.strip() == "I am not allowed to answer that question only.":
        return text

    math_replacements = {
        r'\theta': 'θ', r'\alpha': 'α', r'\beta': 'β', r'\pi': 'π',
        r'\cdot': '·', r'\times': '×', r'\div': '÷', r'\pm': '±',
        r'\leq': '≤', r'\geq': '≥', r'\neq': '≠', r'\approx': '≈',
        r'\sum': '∑', r'\int': '∫', r'\sqrt': '√', r'\infty': '∞',
        r'\tan': 'tan', r'\cot': 'cot', r'\sin': 'sin', r'\cos': 'cos',
        r'\circ': '°', r'\Delta': 'Δ', r'\cong': '≅'
    }
    for lat, uni in math_replacements.items():
        text = text.replace(lat, uni)

    # Automatically strip \text{...} wrappers (e.g. \text{ cm} -> cm)
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)

    sup_map = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
               '+': '⁺', '-': '⁻', 'n': 'ⁿ', 'x': 'ˣ'}

    def replace_exponent(match):
        base = match.group(1)
        exp = match.group(2)
        formatted_exp = "".join([sup_map.get(c, c) for c in exp])
        return f"{base}{formatted_exp}"

    text = re.sub(r'([a-zA-Z0-9\)]+)\^([0-9\+\-]+)', replace_exponent, text)
    text = re.sub(r'\\begin\{[a-zA-Z]+\\}', '', text)
    text = re.sub(r'\\end\{[a-zA-Z]+\\}', '', text)
    text = text.replace('**', '').replace('*', '').replace('$', '')
    text = text.replace('`', '').replace('```', '')
    return text

try:
    font_path = "C:/Windows/Fonts/arial.ttf" if os.name == 'nt' else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont('UnicodeFont', font_path))
        URDU_FONT_AVAILABLE = True
    else:
        URDU_FONT_AVAILABLE = False
except Exception:
    URDU_FONT_AVAILABLE = False


def format_rtl_text(text):
    if any('\u0600' <= char <= '\u06FF' for char in text):
        reshaped_text = arabic_reshaper.reshape(text)
        return get_display(reshaped_text), True
    return text, False


def generate_pdf_bytes(title, text_content, school_name="MODEL HIGH SCHOOL / COLLEGE", user_role="Member"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24
    )

    styles = getSampleStyleSheet()
    final_school_name = "MODEL HIGH SCHOOL / COLLEGE" if user_role == "Member" else school_name
    body_font_name = 'UnicodeFont' if URDU_FONT_AVAILABLE else 'Helvetica'

    school_style = ParagraphStyle(
        'SchoolHeader', parent=styles['Heading2'], fontSize=11, leading=13, alignment=TA_CENTER, textColor=colors.black,
        spaceAfter=1, fontName=body_font_name
    )
    title_style = ParagraphStyle(
        'TestTitle', parent=styles['Heading1'], fontSize=10, leading=12, alignment=TA_CENTER, textColor=colors.black,
        spaceAfter=4, fontName=body_font_name
    )
    ltr_body_style = ParagraphStyle(
        'TestBodyLTR', parent=styles['Normal'], fontSize=8.5, leading=11, alignment=TA_LEFT, textColor=colors.black,
        spaceAfter=1, fontName=body_font_name
    )
    rtl_body_style = ParagraphStyle(
        'TestBodyRTL', parent=styles['Normal'], fontSize=9.5, leading=12.5, alignment=TA_RIGHT, textColor=colors.black,
        spaceAfter=1.5, fontName=body_font_name
    )

    formatted_title, _ = format_rtl_text(title)
    story = [
        Paragraph(f"<b>{final_school_name.upper()}</b>", school_style),
        Paragraph(f"<b>{formatted_title}</b>", title_style),
        Spacer(1, 2)
    ]

    lines = text_content.split('\n')
    current_options = []

    def flush_options():
        if not current_options:
            return
        table_data = []
        if len(current_options) == 4:
            table_data = [
                [current_options[1], current_options[0]],
                [current_options[3], current_options[2]]
            ]
            col_widths = [270, 270]
        else:
            table_data = [current_options]
            col_widths = [540 / max(len(current_options), 1)] * len(current_options)

        t = Table(table_data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ]))
        story.append(t)
        story.append(Spacer(1, 2))
        current_options.clear()

    for line in lines:
        clean_line = line.strip()
        if clean_line:
            clean_line = clean_line.replace('###', '').replace('##', '').strip()
            is_option = any(clean_line.startswith(prefix) for prefix in
                            ['(الف)', '(ب)', '(ج)', '(د)', '(A)', '(B)', '(C)', '(D)', 'a)', 'b)', 'c)'])

            processed_line, is_urdu = format_rtl_text(clean_line)
            safe_text = processed_line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            p_style = rtl_body_style if is_urdu else ltr_body_style

            if is_option:
                current_options.append(Paragraph(safe_text, p_style))
                if len(current_options) == 4:
                    flush_options()
            else:
                flush_options()
                story.append(Paragraph(safe_text, p_style))
        else:
            flush_options()
            story.append(Spacer(1, 1))

    flush_options()
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ---------------------------------------------------------
# 4. SYLLABUS DATA & 78 PAIRS OF WORDS
# ---------------------------------------------------------
STRUCTURED_SYLLABUS = {
    "9 Class": {
        "Mathematics": [
            "Unit 1: Real Numbers", "Unit 2: Logarithms", "Unit 3: Set and Functions",
            "Unit 4: Factorization and Algebraic Expressions", "Unit 5: Linear Equations and Inequalities",
            "Unit 6: Trigonometry", "Unit 7: Coordinate Geometry", "Unit 8: Logic",
            "Unit 9: Similar Figures", "Unit 10: Graphs of Functions", "Unit 11: Loci and Constructions",
            "Unit 12: Information Handling", "Unit 13: Probability"
        ],
        "Physics": [
            "Chapter 1: Physical Quantities and Measurements", "Chapter 2: Kinematics",
            "Chapter 3: Dynamics", "Chapter 4: Turning Effects of Force",
            "Chapter 5: Work, Energy and Power", "Chapter 6: Mechanical Properties of Matter",
            "Chapter 7: Thermal Properties of Matter", "Chapter 8: Magnetism", "Chapter 9: Nature of Science"
        ],
        "Chemistry": [
            "Chapter 1: States of Matter and Phase Changes", "Chapter 2: Atomic Structure",
            "Chapter 3: Chemical Bonding", "Chapter 4: Stoichiometry", "Chapter 5: Energetics",
            "Chapter 6: Equilibrium", "Chapter 7: Acid Base Chemistry", "Chapter 8: Periodic Table and Periodicity",
            "Chapter 9: Group Properties and Elements", "Chapter 10: Environmental Chemistry",
            "Chapter 11: Hydrocarbons", "Chapter 12: Empirical Data Collection and Analysis",
            "Chapter 13: Laboratory and Practical Skills"
        ],
        "Biology": [
            "Chapter 1: The Science of Biology", "Chapter 2: Biodiversity", "Chapter 3: The Cell",
            "Chapter 4: Cell Cycle", "Chapter 5: Tissues, Organs, and Organ Systems",
            "Chapter 6: Biomolecules", "Chapter 7: Enzymes", "Chapter 8: Bioenergetics",
            "Chapter 9: Plant Physiology", "Chapter 10: Reproduction in Plants", "Chapter 11: Biostatistics"
        ],
        "Computer Science": [
            "Unit 1: Introduction to Systems", "Unit 2: Number Systems", "Unit 3: Digital Systems and Logic Design",
            "Unit 4: System Troubleshooting", "Unit 5: Software System", "Unit 6: Introduction to Computer Networks",
            "Unit 7: Computational Thinking", "Unit 8: Web Development with HTML, CSS and JavaScript",
            "Unit 9: Data Science and Data Gathering", "Unit 10: Emerging Technologies in Computer Science",
            "Unit 11: Ethical, Social, and Legal Concerns in Computer Usage", "Unit 12: Entrepreneurship in Digital Age"
        ],
        "Islamiyat": [
            "باب اول: قرآن مجید و حدیث نبوی", "باب دوم: ایمانیات و عبادات",
            "باب سوم: سیرت نبوی (صلی اللہ علیہ وآلہ وسلم)", "باب چہارم: اخلاق و آداب",
            "باب پنجم: حسنِ معاملات", "باب ششم: ہدایت کے سرچشمے", "باب ہفتم: اسلامی تعلیمات اور عصرِ حاضر"
        ],
        "Tarjamatul Quran": [
            "1. سورة الأنعام", "2. سورة الأنفال", "3. سورة التوبة", "4. سورة يونس",
            "5. سورة هود", "6. سورة يوسف", "7. سورة الرعد", "8. سورة إبراهيم",
            "9. سورة الحجر", "10. سورة النحل", "11. سورة الإسراء", "12. سورة الكهف"
        ]
    },
    "10 Class": {
        "Mathematics": [
            "Unit 1: Complex Numbers", "Unit 2: Quadratic Equations and Inequalities",
            "Unit 3: Matrices and Determinants", "Unit 4: Functions and Graphs",
            "Unit 5: Algebraic Fractions", "Unit 6: Vectors in Plane", "Unit 7: Circles",
            "Unit 8: Chords and Arcs of a Circle", "Unit 9: Tangent and Angles of a Circle",
            "Unit 10: Practical Geometry of Circles", "Unit 11: Information Handling", "Unit 12: Probability"
        ],
        "Physics": [
            "Chapter 10: Thermal Physics", "Chapter 11: Transfer of Thermal Energy",
            "Chapter 12: Waves", "Chapter 13: Sound", "Chapter 14: Light",
            "Chapter 15: Electrostatics", "Chapter 16: Electricity", "Chapter 17: Electromagnetism",
            "Chapter 18: Electromagnetic Induction and Electromagnetic Waves", "Chapter 19: Electronics",
            "Chapter 20: Atomic and Nuclear Physics", "Chapter 21: Space and Environment"
        ],
        "Chemistry": [
            "Chapter 14: States of Matter and Phase Changes", "Chapter 15: Stoichiometry",
            "Chapter 16: Electrochemistry", "Chapter 17: Reaction Kinetics", "Chapter 18: Salts",
            "Chapter 19: Nitrogen and Sulphur", "Chapter 20: Water", "Chapter 21: Organic Chemistry",
            "Chapter 22: Hydrocarbons", "Chapter 23: Monohydroxy Alkanes or Alcohols",
            "Chapter 24: Carboxylic Acids", "Chapter 25: Biochemistry", "Chapter 26: Polymers"
        ],
        "Biology": [
            "Chapter 1: Human Respiratory System", "Chapter 2: The Mechanism of Breathing",
            "Chapter 3: Human Blood Circulatory System", "Chapter 4: Human Urinary System",
            "Chapter 5: Coordination", "Chapter 6: Reproduction", "Chapter 7: Inheritance",
            "Chapter 8: Biotechnology", "Chapter 9: Diseases and Immunity", "Chapter 10: Evolution"
        ],
        "Computer Science": [
            "1. OPERATING SYSTEMS: STRUCTURE AND SERVICE", "2. SYSTEM RECOVERY AND ADVANCED MAINTENANCE",
            "3. INTRODUCTION TO PYTHON PROGRAMMING", "4. CONTROL STRUCTURES IN PYTHON",
            "5. INTRODUCTION TO DATA SCIENCE", "6. ARTIFICIAL INTELLIGENCE (AI) AND MACHINE LEARNING (ML)",
            "7. APPLICATIONS OF AI", "8. DIGITAL ENTREPRENEURSHIP"
        ],
        "Pak Studies": [
            "باب 1: پاکستان کی نظریاتی اساس", "باب 2: تحریکِ پاکستان اور قیامِ پاکستان",
            "باب 3: زمین اور ماحول", "باب 4: تاریخِ پاکستان (حصہ اول)", "باب 5: تاریخِ پاکستان (حصہ دوم)"
        ],
        "Tarjamatul Quran": [
            "13. سورة مريم", "14. سورة طه", "15. سورة الأنبياء", "16. سورة الحج",
            "17. سورة المؤمنون", "18. سورة النور", "19. سورة الفرقان", "20. سورة الشعراء",
            "21. سورة النمل", "22. سورة القصص"
        ]
    }
}

ALL_78_PAIRS = [
    "1. Able / Capable", "2. Accept / Except", "3. Access / Excess", "4. Affect / Effect",
    "5. Altar / Alter", "6. Angel / Angle", "7. Bale / Bail", "8. Bear / Bare",
    "9. Birth / Berth", "10. Bough / Bow", "11. Break / Brake", "12. Buy / By",
    "13. Cattle / Kettle", "14. Cell / Sell", "15. Cemetery / Dairy", "16. Childish / Childlike",
    "17. Cousin / Cozen", "18. Dairy / Diary", "19. Decease / Disease", "20. Decent / Descent",
    "21. Desert / Dessert", "22. Device / Devise", "23. Die / Dye", "24. Dose / Doze",
    "25. Due / Dew", "26. Elicit / Illicit", "27. Eligible / Illegible", "28. Emigrant / Immigrant",
    "29. Envelop / Envelope", "30. Fair / Fare", "31. Faint / Feint", "32. Floor / Flour",
    "33. Foul / Fowl", "34. Gate / Gait", "35. Gilt / Guilt", "36. Glance / Glimpse",
    "37. Graceful / Gracious", "38. Hair / Hare", "39. Hart / Heart", "40. Heal / Heel",
    "41. Hear / Here", "42. Herd / Heard", "43. Human / Humane", "44. Idle / Idol",
    "45. Industrial / Industrious", "46. In / Inn", "47. Jewel / Bangle", "48. Key / Quay",
    "49. Liar / Lyre", "50. Lesson / Lessen", "51. Aloud / Allowed", "52. Mail / Male",
    "53. Marry / Merry", "54. Meat / Meet", "55. Metal / Mettle", "56. Miner / Minor",
    "57. None / Nun", "58. Oar / Ore", "59. Pail / Pale", "60. Pain / Pane",
    "61. Pair / Pear", "62. Peace / Piece", "63. Plain / Plane", "64. Population / Density",
    "65. Pray / Prey", "66. Principal / Principle", "67. Profit / Prophet", "68. Rain / Reign",
    "69. Right / Write", "70. Role / Roll", "71. Sail / Sale", "72. Scene / Seen",
    "73. Sea / See", "74. Soar / Sour", "75. Sole / Soul", "76. Stationary / Stationery",
    "77. Story / Storey", "78. Team / Teem"
]

ENGLISH_B_FULL_DATA = {
    "9 Class": {
        "english_a": [
            "Unit 1: The Saviour of Mankind", "Unit 2: Patriotism", "Unit 3: Daffodils (Poem)",
            "Unit 4: Hazrat Asma (R.A)", "Unit 5: Women Empowerment through Entrepreneurship",
            "Unit 6: The Value of Time", "Unit 7: If (Poem)",
            "Unit 8: The Impact of Digital Globalisation on Culture and Economy",
            "Unit 9: Quality Education: A Key to Success",
            "Unit 10: The Silent Predator and the Majestic Prey", "Unit 11: The Dear Departed"
        ],
        "comprehension_passages": [f"Comprehension Passage {i}" for i in range(1, 26)],
        "letters": [f"Letter {i}" for i in range(1, 16)]
    },
    "10 Class": {
        "english_a": [
            "Unit 1: Hazrat Muhammad (PBUH) - An Embodiment of Justice",
            "Unit 2: My Beloved Pakistan (Poem)",
            "Unit 3: Digital Globalisation - Transforming the English Language",
            "Unit 4: The Earth: Act Now for Tomorrow",
            "Unit 5: The Happy Prince", "Unit 6: Drug Abuse", "Unit 7: Time",
            "Unit 8: Pollution-free Pakistan with Greenery All Around",
            "Unit 9: The Road Not Taken (Poem)", "Unit 10: The Three Questions"
        ],
        "pair_of_words": ALL_78_PAIRS,
        "paragraph_writings": [
            "My School", "Girl Guides", "A Visit To A Museum", "A River In Flood",
            "A Pleasant Dream", "How To Keep Our Town Clean?", "An Industrial Exhibition",
            "My Neighbour", "Kitchen Gardening, A Hobby", "Pakistani Women", "Computers",
            "A Fortune-teller", "A Picnic", "A Street Quarrel", "A Visit To A Historical Place",
            "A Visit To A Zoo", "Allama Iqbal (رحمتہ اللہ علیہ)", "The Teacher I Like The Best", "A House On Fire"
        ],
        "essays": [
            "1. My Last Day at School", "2. Sports and Games", "3. My House", "4. Courtesy",
            "5. Libraries", "6. Health", "7. The Monsoon / A Rainy Day", "8. A Scene at a Railway Station",
            "9. A Hockey Match", "10. A Cricket Match", "11. A True Muslim", "12. Life in a Big City",
            "13. Village Life", "14. Television", "15. A Visit to a Hill Station",
            "16. Quaid-e-Azam Muhammad Ali Jinnah", "17. Tolerance", "18. Boy Scouts",
            "19. My Favourite Book", "20. My Ambition", "21. My Hobby", "22. Our School Canteen",
            "23. My Best Friend", "24. A Rain Storm", "25. Our National Poet", "26. How to Make Tea?"
        ],
        "translation_urdu_to_eng": [f"Translation Paragraph {i}" for i in range(1, 20)],
        "direct_indirect_types": ["Affirmative Sentences", "Negative Sentences", "Interrogative Sentences"]
    }
}

URDU_B_FULL_DATA = {
    "9 Class": {
        "urdu_a": [
            "سبق 1: اخلاقِ حسنہ", "سبق 2: اپنی مدد آپ", "سبق 3: کلیم اور مرزا ظاہر دار بیگ",
            "سبق 4: نام دیو مالی", "سبق 5: آرام و سکون", "سبق 6: بنفشہ",
            "سبق 7: کالم خلاؤں میں سفر کیسے کرتے ہیں؟", "سبق 8: ابتدائی حساب",
            "نظم 1: حمد", "نظم 2: نعت", "غزل 1: میر تقی میر", "غزل 2: اسد اللہ خان غالب"
        ],
        "stories": [
            "1. شیر کا گھر، عقل مند بڑھئی", "2. گیدڑ کی مکاری", "3. جس کا کام اسی کو سوہے",
            "4. سچ کی برکت", "5. اتفاق کی برکت", "6. جھوٹ کی سزا", "7. عقل مند بیوی"
        ],
        "applications": [
            "1. ضروری کام کی وجہ سے چھٹی کی درخواست", "2. بیماری کی وجہ سے طویل رخصت",
            "3. فیس معافی کی درخواست", "4. محلے کی صفائی کے لیے درخواست"
        ]
    },
    "10 Class": {
        "urdu_a": [
            "سبق 1: پاکستان کی نظریاتی اساس", "سبق 2: نظریہ پاکستان",
            "سبق 3: 14 اگست 1947ء کا ماحول", "سبق 4: پاکستان کی تاریخ"
        ],
        "essays": ["مضمون: حبِ وطن", "مضمون: وقت کی پابندی", "مضمون: علامہ اقبال", "مضمون: سائنس کے کرشمے"],
        "comprehension_passages": [f"تفہیمِ عبارت نمبر {i}" for i in range(1, 11)]
    }
}

# ---------------------------------------------------------
# 5. SIDEBAR NAVIGATION & TOP BAR SIGN OUT
# ---------------------------------------------------------
with st.sidebar:
    st.title("⚡ Brienn Tizerr.pk")
    st.caption("Version 1.7 / Production Build")

    st.markdown("---")
    st.markdown("### 👤 Google Account Details")
    st.write(f"**Name:** {user_name}")
    st.write(f"**Email:** {user_email}")
    st.write(f"**Attached Phone:** {current_user_record.get('phone', 'N/A')}")
    st.write(f"**Role:** {user_role} {'🚫 (Restricted)' if user_is_banned else ''}")

    if st.button("🚪 Sign Out", key="sidebar_sign_out_btn"):
        st.logout()

    today_str = datetime.now().strftime("%Y-%m-%d")
    used_today = st.session_state["daily_total_tests"].get(today_str, 0)
    daily_cap = 5 if (user_role == "Subscribed" and not user_is_banned) else (
        999 if (user_role == "Admin" and not user_is_banned) else 2)
    if user_role != "Admin" or user_is_banned:
        st.write(f"**Daily Usage:** {used_today} / {daily_cap} tests")

    # --- TOKEN USAGE DISPLAY (AUTO-RESETS DAILY) ---
    st.markdown("---")
    st.markdown("### 📊 API Token Usage (Daily)")
    st.write(f"**Total Today's Tokens:** {st.session_state['total_tokens_used']:,}")
    if st.session_state["last_test_tokens"] > 0:
        st.caption(
            f"Prompt: {st.session_state['last_prompt_tokens']:,} | Comp: {st.session_state['last_completion_tokens']:,}")

    # --- ADMIN ELEVATION (ACCESSIBLE EVEN IF BANNED — AUTO-UNBANS ON VALID KEY) ---
    st.markdown("---")
    st.markdown("### 🔑 Admin Elevation")
    passkey_input = st.text_input("Enter Admin Passkey", type="password")
    if st.button("Claim Admin Privileges"):
        if passkey_input == st.session_state["admin_passkey"]:
            supabase.table("users").update({
                "role": "Admin",
                "subscribed_at": 0,
                "is_banned": False,
                "rejection_count": 0
            }).eq("email", user_email).execute()
            st.success("Admin Elevation Granted & Account Unrestricted!")
            st.rerun()
        else:
            st.error("Invalid Passkey")

# Top bar user greeting & sign out
top_c1, top_c2 = st.columns([5, 1])
with top_c1:
    st.caption(f"Signed in as **{user_name}** ({user_email})")
with top_c2:
    if st.button("🚪 Sign Out", key="top_sign_out_btn"):
        st.logout()

# ---------------------------------------------------------
# 6. MAIN APPLICATION TABS
# ---------------------------------------------------------
tabs = ["📝 Test Generator", "💾 Saved Tests", "📩 Feedback", "❓ Help & FAQ"]
if user_role == "Admin" and not user_is_banned:
    tabs.append("⚙️ Admin Dashboard")

selected_tab = st.tabs(tabs)

# ---------------------------------------------------------
# TAB 1: TEST GENERATOR
# ---------------------------------------------------------
with selected_tab[0]:
    if user_is_banned:
        st.markdown("""
        <div class="banned-banner">
            <h2 style="margin:0; color:#FF4B4B !important;">🚫 Account Restricted — Subscription Access Disabled</h2>
            <p style="margin-top:8px;">
                Your account has been restricted by the administrator due to repeated invalid or fake payment attempts.<br><br>
                • <b>Current Access Level:</b> Standard Member (<b>2 Tests per day</b> total, PDF export enabled).
            </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="sub-banner">
            <h2 style="margin:0;">💎 Membership Plans & Limits</h2>
            <p style="margin-top:5px;">
                • <b>Members (Free):</b> <b>2 Tests per day</b> total (across any class or subject). PDF export enabled.<br>
                • <b>Subscribed:</b> <b>5 Tests per day</b> total + Custom School Name headers & direct test question editing!<br>
                • <b>Payment Policy:</b> Only one active request is allowed at a time. If rejected, you may submit a new receipt. Frequent fake receipts result in an automatic account ban.
            </p>
        </div>
        """, unsafe_allow_html=True)

        req_res = supabase.table("requests").select("*").eq("user_email", user_email).eq("status", "Pending").execute()
        user_pending_req = req_res.data[0] if req_res.data else None

        with st.expander("💳 Subscription & JazzCash Activation Panel"):
            if user_pending_req:
                st.warning(
                    f"⏳ **Active Request Pending:** You already have a request pending review (Type: **{user_pending_req.get('request_type', 'N/A')}**). You cannot submit another payment request until the admin reviews this one.")
            else:
                sc1, sc2 = st.columns(2)
                with sc1:
                    st.markdown(f"""
                    <div class="jazzcash-box">
                        <h4 style="margin-top:0; color:#FF4B4B !important;">📱 JazzCash Payment Details</h4>
                        <p style="margin-bottom:4px;"><b>JazzCash Number:</b> <code>{JAZZCASH_NUMBER}</code></p>
                        <p style="margin-bottom:4px;"><b>Account Title:</b> {JAZZCASH_TITLE}</p>
                        <p style="margin-bottom:0;"><b>Subscription Fee:</b> Rs. 400 / Month (5 Tests/Day + Editing)</p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.caption(
                        "Send Rs. 400 to the JazzCash number above, or select Free Request to state your reason.")

                with sc2:
                    st.markdown("#### Submit Request")
                    req_mode = st.radio("Select Option", ["Paid Subscription (Rs. 400)", "Free Request"])
                    st.text_input("Account Email (Auto-Linked)", value=user_email, disabled=True)

                    if "Paid" in req_mode:
                        user_phone_number = st.text_input(
                            "Your Phone Number (Gets attached to your email)",
                            value=current_user_record.get("phone", ""),
                            placeholder="e.g. 03001234567"
                        )
                        submit_label = "Attach Number & Submit Paid Request"
                    else:
                        free_reason_input = st.text_area(
                            "Reason for Free Subscription",
                            placeholder="Explain why you are requesting free access..."
                        )
                        submit_label = "Submit Free Request"

                    if st.button(submit_label):
                        if "Paid" in req_mode:
                            if user_phone_number.strip():
                                clean_phone = user_phone_number.strip()
                                supabase.table("users").update({"phone": clean_phone}).eq("email", user_email).execute()

                                supabase.table("requests").insert({
                                    "id": f"r_{int(time.time())}",
                                    "user_email": user_email,
                                    "request_type": "Paid",
                                    "sender_number": clean_phone,
                                    "reason": "",
                                    "status": "Pending"
                                }).execute()

                                if not current_user_record.get("provisional_claimed", False):
                                    st.session_state["provisional_tests_remaining"] = 4
                                    supabase.table("users").update({"provisional_claimed": True}).eq("email",
                                                                                                     user_email).execute()
                                    st.success(
                                        f"🎉 Number ({clean_phone}) attached to {user_email}! You've unlocked 4 provisional tests while waiting for admin review.")
                                else:
                                    st.success("🎉 Payment request submitted successfully! Pending admin verification.")
                                st.rerun()
                            else:
                                st.warning("Please enter your phone number so it can be attached to your email.")
                        else:
                            if free_reason_input.strip():
                                clean_reason = free_reason_input.strip()
                                supabase.table("requests").insert({
                                    "id": f"r_{int(time.time())}",
                                    "user_email": user_email,
                                    "request_type": "Free",
                                    "sender_number": "N/A (Free)",
                                    "reason": clean_reason,
                                    "status": "Pending"
                                }).execute()
                                st.success(
                                    "🎉 Free subscription request submitted successfully with your reason! Pending admin review.")
                                st.rerun()
                            else:
                                st.warning("Please provide a reason for your free subscription request.")

    st.markdown("---")
    st.markdown("## 📝 Test Generator")

    user_is_subscriber_or_admin = (user_role in ["Subscribed", "Admin"]) and not user_is_banned

    if user_is_subscriber_or_admin:
        school_name_input = st.text_input("School / Institution Name (Custom Header)",
                                          value="Model High School / College")
    else:
        school_name_input = "Model High School / College"
        if not user_is_banned:
            st.info(
                "💡 **Subscriber Perk:** Upgrade to Subscribed to unlock **5 tests/day**, customize your own School Name header, and edit test questions before downloading!")

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_class = st.selectbox("Select Class", ["9 Class", "10 Class"])
    with col2:
        all_subjects = list(STRUCTURED_SYLLABUS[selected_class].keys()) + ["English", "Urdu"]
        selected_subject = st.selectbox("Select Subject", all_subjects)
    with col3:
        medium = st.selectbox("Select Medium", ["English Medium", "Urdu Medium"])

    test_type = st.radio("Test Type", ["Chapter Wise", "Half Book", "Full Book"])
    difficulty = st.select_slider("Difficulty Mode", options=["Easy", "Medium", "Hard"])

    custom_test_instructions = st.text_input(
        "Custom Test Instructions / Special Requests (Optional)",
        placeholder="e.g., Make it 30 marks, include 5 short questions, focus heavily on numericals..."
    )

    selected_chapters = []

    if test_type == "Chapter Wise":
        if selected_subject == "English":
            st.markdown("---")
            st.markdown(f"### 🇬🇧 English Syllabus Selection ({selected_class})")
            eng_tab1, eng_tab2 = st.tabs(["English A (Units)", "English B (Grammar & Composition)"])
            eng_data = ENGLISH_B_FULL_DATA[selected_class]
            with eng_tab1:
                selected_chapters = st.multiselect("Select Units", eng_data["english_a"])
            with eng_tab2:
                if selected_class == "9 Class":
                    st.multiselect("Comprehension Passages (1-25)", eng_data["comprehension_passages"])
                    st.multiselect("Letters Selection (1-15)", eng_data["letters"])
                else:
                    st.markdown("#### 📝 Complete 78 Pair of Words Selection")
                    selected_pairs = st.multiselect("Select Pair of Words (Leave empty to include all 78)",
                                                    eng_data["pair_of_words"], default=[])
                    if selected_pairs:
                        selected_chapters.extend(selected_pairs)
                    else:
                        selected_chapters.extend(eng_data["pair_of_words"])
                    st.multiselect("Paragraph Writings", eng_data["paragraph_writings"])
                    st.multiselect("Select Essays", eng_data["essays"])

        elif selected_subject == "Urdu":
            st.markdown("---")
            st.markdown(f"### 🇵🇰 Urdu Syllabus Selection ({selected_class})")
            u_tab1, u_tab2 = st.tabs(["Urdu A (نثر و نظم)", "Urdu B (قواعد و انشا)"])
            urdu_data = URDU_B_FULL_DATA[selected_class]
            with u_tab1:
                selected_chapters = st.multiselect("Select Lessons & Poems", urdu_data["urdu_a"])
            with u_tab2:
                if selected_class == "9 Class":
                    st.multiselect("کہانی نویسی (Stories)", urdu_data["stories"])
                    st.multiselect("درخواست نویسی (Applications)", urdu_data["applications"])
                else:
                    st.multiselect("مضمون نویسی (Urdu Essays)", urdu_data["essays"])

        else:
            st.markdown("---")
            selected_chapters = st.multiselect("Select Chapters", STRUCTURED_SYLLABUS[selected_class][selected_subject])
    else:
        selected_chapters = [f"{test_type} Scope"]

    can_generate = True
    today_str = datetime.now().strftime("%Y-%m-%d")
    tests_generated_today = st.session_state["daily_total_tests"].get(today_str, 0)

    # --- REAL-WORLD 10-MINUTE COOLDOWN CHECK ---
    COOLDOWN_MINUTES = 10
    if st.session_state["last_generation_time"] and isinstance(st.session_state["last_generation_time"], datetime):
        time_elapsed = (datetime.now() - st.session_state["last_generation_time"]).total_seconds()
        in_cooldown = time_elapsed < (COOLDOWN_MINUTES * 60)
    else:
        in_cooldown = False
        time_elapsed = 999999

    if in_cooldown and user_role != "Admin":
        remaining_seconds = int((COOLDOWN_MINUTES * 60) - time_elapsed)
        remaining_minutes = remaining_seconds // 60
        rem_sec = remaining_seconds % 60
        can_generate = False
        st.warning(
            f"⏳ **Cool-down Active:** Please wait **{remaining_minutes}m {rem_sec}s** before generating your next test.")

    if user_role == "Member" or user_is_banned:
        if not user_is_banned and st.session_state["provisional_tests_remaining"] > 0:
            st.info(
                f"⚡ Provisional Bonus Access Active: **{st.session_state['provisional_tests_remaining']}** tests remaining.")
        elif tests_generated_today >= 2:
            can_generate = False
            if user_is_banned:
                st.error(
                    "🚫 Daily limit reached (**2 tests per day** across all subjects/classes). Your quota resets tomorrow.")
            else:
                st.error(
                    "🚫 Daily free limit reached (**2 tests per day** across all subjects/classes). Submit a subscription request above to unlock provisional tests or upgrade to 5 tests/day!")

    elif user_role == "Subscribed":
        if tests_generated_today >= 5:
            can_generate = False
            st.warning(
                "⏳ Subscribed Daily Limit Reached (**5 tests per day** across all subjects/classes). Your quota resets tomorrow!")

    if st.button("⚡ Generate Test Paper", disabled=(not can_generate)):
        st.session_state["show_quota_help_inline"] = False
        with st.spinner("Generating Test Paper & Answer Key with Gemini API..."):

            if selected_subject == "Urdu" or medium == "Urdu Medium":
                language_rule = "Write strictly in native Urdu script (اردو) following PCTB curriculum."
            else:
                language_rule = "Write in official English script." if medium == "English Medium" else "Write in official Urdu script."

            prompt = f"""
            Generate a {selected_class} {selected_subject} test paper.
            - Medium: {medium}
            - Scope: {selected_chapters}
            - Type: {test_type}
            - Difficulty: {difficulty}
            - Notes: {custom_test_instructions}
            - Rules: {language_rule}

            At the end, separated by '====================', provide the step-by-step Answer Key.
            """

            try:
                model = genai.GenerativeModel("models/gemini-3.6-flash")
                response = model.generate_content(
                    prompt,
                    generation_config={"max_output_tokens": 4096}
                )

                # --- TRACK TOKEN USAGE ---
                p_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) if hasattr(response,
                                                                                                "usage_metadata") else 0
                c_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) if hasattr(response,
                                                                                                    "usage_metadata") else 0
                t_tokens = getattr(response.usage_metadata, "total_token_count", 0) if hasattr(response,
                                                                                               "usage_metadata") else 0

                st.session_state["last_prompt_tokens"] = p_tokens
                st.session_state["last_completion_tokens"] = c_tokens
                st.session_state["last_test_tokens"] = t_tokens
                st.session_state["total_tokens_used"] += t_tokens

                cleaned_output = clean_latex_formatting(response.text)

                if cleaned_output.strip() == "I am not allowed to answer that question only.":
                    st.warning("⚠️ I am not allowed to answer that question only.")
                else:
                    if not user_is_banned and user_role == "Member" and st.session_state[
                        "provisional_tests_remaining"] > 0:
                        st.session_state["provisional_tests_remaining"] -= 1
                    else:
                        st.session_state["daily_total_tests"][today_str] = tests_generated_today + 1

                    st.session_state["last_generation_time"] = datetime.now()

                    if "====================" in cleaned_output:
                        parts = cleaned_output.split("====================")
                        st.session_state["current_test"] = parts[0].strip()
                        st.session_state["current_answer_key"] = parts[1].strip()
                    else:
                        st.session_state["current_test"] = cleaned_output
                        st.session_state["current_answer_key"] = "Answer Key generated with test paper."

                    st.session_state["editable_test_text"] = st.session_state["current_test"]
                    st.success("Test Paper & Answer Key Generated Successfully!")
            except Exception as e:
                err_msg = str(e).lower()
                if "429" in err_msg or "quota" in err_msg or "resource_exhausted" in err_msg or "limit" in err_msg:
                    st.error(
                        "⏳ Daily AI generation capacity has been reached! Our servers refresh their daily quota automatically.")
                    if st.button("❓ Why did this happen? (Click for Help)", key="quota_help_trigger"):
                        st.session_state["show_quota_help_inline"] = True
                else:
                    st.error(
                        "⚠️ An unexpected error occurred while generating your test. Please try again in a moment or check the Help & FAQ tab.")

    if st.session_state.get("show_quota_help_inline"):
        st.info("""
        **ℹ️ Why am I seeing this message?**
        * **Daily AI Token Limit:** To keep Brienn Tizerr.pk fast and accessible, our AI test generator operates on a shared daily token allowance.
        * **When does it reset?** The daily limit resets automatically every 24 hours (at 12:00 PM Pakistan Standard Time / Midnight PT).
        * **What can I do right now?** You can still view, edit, print, and download all of your previously generated tests inside the **💾 Saved Tests** tab! For more info, visit the **❓ Help & FAQ** tab.
        """)

    if "current_test" in st.session_state and st.session_state["current_test"] and st.session_state[
        "current_test"].strip() != "I am not allowed to answer that question only.":
        st.markdown("### 📄 Test Paper Preview & Save")

        # --- DISPLAY INPUT & OUTPUT TOKENS BELOW EVERY TEST ---
        st.markdown(f"""
        <div style="background-color: #161B22; border: 1px solid #00FF66; padding: 10px 15px; border-radius: 6px; margin-bottom: 15px;">
            <span style="color: #00FF66; font-weight: bold;">📊 API Token Usage (This Generation):</span><br>
            • <b>Input (Prompt) Tokens:</b> {st.session_state.get('last_prompt_tokens', 0):,}<br>
            • <b>Output (Completion) Tokens:</b> {st.session_state.get('last_completion_tokens', 0):,}<br>
            • <b>Total Tokens Used:</b> {st.session_state.get('last_test_tokens', 0):,} (Daily Total: {st.session_state.get('total_tokens_used', 0):,})
        </div>
        """, unsafe_allow_html=True)

        if not st.session_state["editable_test_text"] and "current_test" in st.session_state:
            st.session_state["editable_test_text"] = st.session_state["current_test"]

        default_save_name = f"{selected_class} {selected_subject} ({medium})"
        user_save_title_input = st.text_input("Name Your Test (to remember it later)", value=default_save_name)

        if user_is_subscriber_or_admin:
            st.caption("✨ Subscriber Mode: You can freely edit questions, remove items, or replace text below.")
            edited_test_content = st.text_area("Edit Paper Content", height=350, key="editable_test_text")
        else:
            st.caption("🔒 Free Member Mode: Previewing generated test. Upgrade to Subscribed to unlock direct editing.")
            edited_test_content = st.text_area("Test Content (Read-Only for Members)",
                                               value=st.session_state["editable_test_text"], height=350, disabled=True,
                                               key="readonly_test_box")

        # --- HIDDEN / COLLAPSIBLE ANSWER KEY EXPANDER ---
        if "current_answer_key" in st.session_state and st.session_state["current_answer_key"]:
            with st.expander("🔑 View Answer Key & Solution Guide"):
                if "editable_answer_box" not in st.session_state:
                    st.session_state["editable_answer_box"] = st.session_state["current_answer_key"]
                edited_ans_content = st.text_area("Edit Answer Key (Optional)", height=250, key="editable_answer_box")

                ak_col1, ak_col2 = st.columns(2)
                with ak_col1:
                    print_ans_html = f"""
                        <script>
                        function printAnswerKey() {{
                            var w = window.open('', '_print_ak', 'height=600,width=800');
                            w.document.write('<html><head><title>{user_save_title_input} - Answer Key</title></head><body>');
                            w.document.write('<h2>{user_save_title_input} - Answer Key</h2><pre style="font-family:sans-serif; white-space:pre-wrap;">{edited_ans_content}</pre>');
                            w.document.write('</body></html>');
                            w.document.close();
                            w.focus();
                            setTimeout(function(){{w.print();w.close();}}, 250);
                        }}
                        </script>
                        <button onclick="printAnswerKey()" style="
                            background-color: #00FF66; color: #0E1117; padding: 10px 15px; 
                            border: none; font-weight: bold; border-radius: 5px; cursor: pointer; width: 100%;">
                            🖨️ Print Answer Key
                        </button>
                    """
                    st.components.v1.html(print_ans_html, height=50)

                with ak_col2:
                    ans_pdf_data = generate_pdf_bytes(f"{user_save_title_input} - Answer Key", edited_ans_content,
                                                      school_name=school_name_input, user_role=user_role)
                    st.download_button(
                        label="📥 Download Answer Key PDF",
                        data=ans_pdf_data,
                        file_name=f"{user_save_title_input.replace(' ', '_')}_AnswerKey.pdf",
                        mime="application/pdf",
                        key="download_ans_pdf_btn"
                    )

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            if st.button("💾 Save Test & Answer Key to Saved Tests Box"):
                final_content_to_save = st.session_state.get("editable_test_text", edited_test_content)
                combined_content = final_content_to_save + "\n\n====================\nANSWER KEY:\n====================\n\n" + st.session_state.get(
                    "editable_answer_box", "")
                supabase.table("saved_tests").insert({
                    "user_email": user_email,
                    "name": user_save_title_input,
                    "content": combined_content
                }).execute()
                st.success(f"✅ Test and Answer Key successfully saved as '{user_save_title_input}' in Supabase!")

        with col_s2:
            content_for_pdf = st.session_state.get("editable_test_text", edited_test_content)
            pdf_data = generate_pdf_bytes(
                user_save_title_input,
                content_for_pdf,
                school_name=school_name_input,
                user_role=user_role
            )
            st.download_button(
                label="📥 Download Test PDF",
                data=pdf_data,
                file_name=f"{user_save_title_input.replace(' ', '_')}.pdf",
                mime="application/pdf",
                key="download_pdf_btn_box"
            )

        st.caption(
            "💡 **Note:** Please review and customize your test paper above before downloading. Once exported as a PDF, the file cannot be edited.")

# ---------------------------------------------------------
# TAB 2: SAVED TESTS
# ---------------------------------------------------------
with selected_tab[1]:
    st.markdown("## 💾 Saved Tests Box")
    saved_res = supabase.table("saved_tests").select("*").eq("user_email", user_email).execute()
    saved_tests_list = saved_res.data

    if not saved_tests_list:
        st.info(
            "No saved tests found in Supabase yet. Generate a test and click 'Save Test & Answer Key' to store it here.")
    else:
        st.markdown(
            "Your saved tests are listed below. You can rename them, print them directly using your browser, or download them as PDFs.")

        for idx, t in enumerate(saved_tests_list):
            with st.expander(f"📄 {t.get('name', f'Saved Test #{idx + 1}')} (Click to open)"):

                new_title = st.text_input("Rename Test Title", value=t.get("name", f"Test #{idx + 1}"),
                                          key=f"rename_input_{t['id']}")
                edited_saved_content = st.text_area("Test & Answer Key Content", value=t["content"], height=250,
                                                    key=f"saved_box_{t['id']}")

                if st.button("💾 Update Saved Test", key=f"update_saved_{t['id']}"):
                    supabase.table("saved_tests").update({"name": new_title, "content": edited_saved_content}).eq("id",
                                                                                                                  t[
                                                                                                                      "id"]).execute()
                    st.success("Test updated successfully!")
                    st.rerun()

                rc1, rc2, rc3 = st.columns(3)
                with rc1:
                    print_html = f"""
                        <script>
                        function printTest_{t['id']}() {{{{
                            var w = window.open('', '_print', 'height=600,width=800');
                            w.document.write('<html><head><title>{new_title}</title></head><body>');
                            w.document.write('<h2>{new_title}</h2><p style="text-align: right;">Date: {t.get("created_at", "")[:10]}</p><hr>');
                            w.document.write('{edited_saved_content}');
                            w.document.write('</body></html>');
                            w.document.close();
                            w.focus();
                            setTimeout(function(){{{{w.print();w.close();}}}}, 250);
                        }}}}
                        </script>
                        <button onclick="printTest_{t['id']}()" style="
                            background-color: #00FF66; color: #0E1117; padding: 10px 15px; 
                            border: none; font-weight: bold; border-radius: 5px; cursor: pointer; width: 100%;">
                            🖨️ Print Test
                        </button>
                    """
                    st.components.v1.html(print_html, height=50)

                with rc2:
                    pdf_bytes_saved = generate_pdf_bytes(new_title, edited_saved_content, user_role=user_role)
                    st.download_button(
                        label="📥 PDF",
                        data=pdf_bytes_saved,
                        file_name=f"{new_title.replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        key=f"dl_pdf_{t['id']}"
                    )

                with rc3:
                    if st.button(f"🗑️ Delete", key=f"del_saved_{t['id']}"):
                        supabase.table("saved_tests").delete().eq("id", t["id"]).execute()
                        st.success("Test deleted successfully!")
                        st.rerun()

# ---------------------------------------------------------
# TAB 3: USER FEEDBACK SUBMISSION
# ---------------------------------------------------------
with selected_tab[2]:
    st.markdown("## 📩 User Feedback & Support")
    st.markdown("Have a suggestion, found a bug, or need help? Send a message directly to the admin.")

    with st.form("feedback_form_key"):
        feedback_email = st.text_input("Your Email Address", value=user_email)
        feedback_category = st.selectbox("Feedback Type", ["Bug Report", "Feature Request", "General Query", "Other"])
        feedback_message = st.text_area("Your Message / Feedback", placeholder="Type your message here...")

        submit_feedback = st.form_submit_button("Submit Feedback")

        if submit_feedback:
            if feedback_email and feedback_message:
                supabase.table("feedbacks").insert({
                    "email": feedback_email,
                    "category": feedback_category,
                    "message": feedback_message,
                    "admin_reply": "",
                    "status": "Unread"
                }).execute()
                st.success("✅ Thank you! Your feedback has been saved to Supabase successfully.")
            else:
                st.warning("⚠️ Please make sure your email and message fields are filled out.")

    fb_res = supabase.table("feedbacks").select("*").eq("email", user_email).execute()
    user_msgs = fb_res.data
    if user_msgs:
        st.markdown("---")
        st.markdown("### 📬 Your Submitted Messages & Admin Replies")
        for msg in user_msgs:
            st.write(f"**[{msg['category']}]**: {msg['message']}")
            if msg.get("admin_reply"):
                st.success(f"💬 **Admin Reply:** {msg['admin_reply']}")
            else:
                st.info("⏳ Status: Waiting for admin reply...")

# ---------------------------------------------------------
# TAB 4: HELP & FAQ
# ---------------------------------------------------------
with selected_tab[3]:
    st.markdown("## ❓ Help Center & Frequently Asked Questions")
    st.markdown("Everything you need to know about generating tests, customizing papers, and resolving common errors.")

    st.markdown("""
    <div class="help-card">
        <h4 style="margin-top:0; color:#00FF66 !important;">⏳ Error: "Daily AI Generation Capacity Reached / Out of API Tokens"</h4>
        <p style="margin-bottom:0;">
            <b>Why does this happen?</b> Our AI engine uses a daily token allowance to generate customized PCTB test papers and answer keys. When heavy usage exhausts the daily limit, new test generation pauses temporarily.<br><br>
            <b>When does it reset?</b> The token limit resets automatically every 24 hours (at <b>12:00 PM Pakistan Standard Time / Midnight PT</b>).<br><br>
            <b>What can I do in the meantime?</b> You can still open, edit, print, and download all of your existing tests in the <b>💾 Saved Tests</b> tab without using any tokens.
        </p>
    </div>

    <div class="help-card">
        <h4 style="margin-top:0; color:#00FF66 !important;">✏️ Customizing Your Test Paper Before Downloading</h4>
        <p style="margin-bottom:0;">
            • <b>Edit Before Export:</b> Subscribed users can freely edit questions, change marks, or adjust headings directly inside the preview box before clicking <b>Download Test PDF</b>.<br>
            • <b>PDF Locking:</b> Once a test is downloaded as a PDF, it is formatted into a print-ready document and cannot be edited inside the PDF file. Always make your changes in the editor first!
        </p>
    </div>

    <div class="help-card">
        <h4 style="margin-top:0; color:#00FF66 !important;">🔑 Where is the Answer Key?</h4>
        <p style="margin-bottom:0;">
            Every time you generate a test paper, its step-by-step Answer Key is automatically created at the same time. Simply click the <b>🔑 View Answer Key & Solution Guide</b> bar underneath the test preview to view, print, or download it separately.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.info("""
    💡 **Have a question that isn't listed here, or want to suggest a new feature?**

    Head over to the **📩 Feedback** tab and send us your question or feature idea! We regularly review your messages and add helpful answers and brand-new features straight into this Help Center.
    """)

# ---------------------------------------------------------
# TAB 5: ADMIN DASHBOARD
# ---------------------------------------------------------
if user_role == "Admin" and not user_is_banned:
    admin_tab_index = tabs.index("⚙️ Admin Dashboard")
    with selected_tab[admin_tab_index]:
        st.markdown("## ⚙️ Admin Dashboard")
        st.info(f"📊 **Today's Total Session Tokens:** {st.session_state['total_tokens_used']:,} tokens")
        atabs = st.tabs(
            ["👥 Users Management", "💳 Pending Requests", "🚫 Blocked Users", "📩 User Messages", "🔐 Security & Passkey"])

        with atabs[0]:
            st.markdown("### User Control & Search")
            u_search = st.text_input("🔍 Search User Database (by Email or Phone)")

            users_res = supabase.table("users").select("*").execute()
            all_db_users = users_res.data

            for usr in all_db_users:
                if not usr["is_banned"]:
                    phone_str = usr.get("phone", "")
                    matches_search = (
                            not u_search
                            or u_search.lower() in usr["email"].lower()
                            or u_search.lower() in phone_str.lower()
                    )
                    if (not usr["is_deleted"] or u_search) and matches_search:
                        c1, c2, c3, c4, c5, c6 = st.columns([3, 1, 1, 1, 1, 1])

                        phone_badge = f" | 📱 {phone_str}" if phone_str else ""
                        rej_count_badge = f" | ⚠️ Rejections: {usr.get('rejection_count', 0)}"
                        c1.write(
                            f"**{usr['email']}**{phone_badge}{rej_count_badge} {'(Soft Deleted)' if usr['is_deleted'] else ''}")
                        c2.write(usr["role"])

                        role = usr["role"]

                        if role == "Member":
                            if c3.button("Make Subscribed", key=f"sub_{usr['id']}"):
                                new_ts = int(time.time())
                                supabase.table("users").update({"role": "Subscribed", "subscribed_at": new_ts}).eq("id",
                                                                                                                   usr[
                                                                                                                       "id"]).execute()
                                st.success(f"Upgraded {usr['email']} to Subscribed!")
                                st.rerun()
                            if c4.button("Make Admin", key=f"adm_{usr['id']}"):
                                supabase.table("users").update({"role": "Admin", "subscribed_at": 0}).eq("id", usr[
                                    "id"]).execute()
                                st.success(f"Promoted {usr['email']} to Admin!")
                                st.rerun()

                        elif role == "Subscribed":
                            if c3.button("Make Admin", key=f"prom_{usr['id']}"):
                                supabase.table("users").update({"role": "Admin", "subscribed_at": 0}).eq("id", usr[
                                    "id"]).execute()
                                st.success(f"Promoted {usr['email']} to Admin!")
                                st.rerun()
                            if c4.button("Demote to Member", key=f"dem_{usr['id']}"):
                                supabase.table("users").update({"role": "Member", "subscribed_at": 0}).eq("id", usr[
                                    "id"]).execute()
                                st.warning(f"Demoted {usr['email']} to Member.")
                                st.rerun()

                        elif role == "Admin":
                            if c3.button("Demote to Subscribed", key=f"dsys_{usr['id']}"):
                                new_ts = int(time.time())
                                supabase.table("users").update({"role": "Subscribed", "subscribed_at": new_ts}).eq("id",
                                                                                                                   usr[
                                                                                                                       "id"]).execute()
                                st.warning(f"Demoted {usr['email']} to Subscribed.")
                                st.rerun()
                            if c4.button("Demote to Member", key=f"dmem_{usr['id']}"):
                                supabase.table("users").update({"role": "Member", "subscribed_at": 0}).eq("id", usr[
                                    "id"]).execute()
                                st.warning(f"Demoted {usr['email']} directly to Member.")
                                st.rerun()

                        if c5.button("Delete", key=f"sdel_{usr['id']}"):
                            supabase.table("users").update({"is_deleted": True}).eq("id", usr["id"]).execute()
                            st.info(f"User {usr['email']} hidden from active list.")
                            st.rerun()

                        if c6.button("🚫 Ban", key=f"ban_{usr['id']}"):
                            supabase.table("users").update(
                                {"is_banned": True, "role": "Member", "subscribed_at": 0}).eq("id", usr["id"]).execute()
                            st.error(f"User {usr['email']} banned and demoted to Member!")
                            st.rerun()

        with atabs[1]:
            st.markdown("### Pending Access Requests")
            reqs_res = supabase.table("requests").select("*").eq("status", "Pending").execute()
            pending_requests = reqs_res.data

            if not pending_requests:
                st.info("No pending requests.")
            else:
                for req in pending_requests:
                    rc1, rc2, rc3 = st.columns([4, 1, 1])

                    target_user_res = supabase.table("users").select("*").eq("email", req["user_email"]).execute()
                    target_user = target_user_res.data[0] if target_user_res.data else None
                    rej_count = target_user.get("rejection_count", 0) if target_user else 0
                    warning_tag = f" ⚠️ [Fake Payment Count: {rej_count}]" if rej_count > 0 else ""

                    if req["request_type"] == "Free":
                        req_details = f"Free Request — Reason: *{req.get('reason', 'N/A')}*"
                    else:
                        req_details = f"Paid Request — Phone: **{req.get('sender_number', 'N/A')}**{warning_tag}"

                    rc1.write(f"**{req['user_email']}** [{req['request_type']}] — {req_details}")

                    if rc2.button("Approve", key=f"app_{req['id']}"):
                        supabase.table("requests").update({"status": "Approved"}).eq("id", req["id"]).execute()
                        if target_user:
                            new_ts = time.time()
                            supabase.table("users").update(
                                {"role": "Subscribed", "subscribed_at": new_ts, "rejection_count": 0}).eq("email", req[
                                "user_email"]).execute()
                        st.success(f"Approved subscription for {req['user_email']}!")
                        st.rerun()

                    if rc3.button("Reject", key=f"rej_{req['id']}"):
                        supabase.table("requests").update({"status": "Rejected"}).eq("id", req["id"]).execute()
                        if target_user:
                            new_rej_count = rej_count + 1
                            if new_rej_count >= 3:
                                supabase.table("users").update(
                                    {"is_banned": True, "role": "Member", "rejection_count": new_rej_count}).eq("email",
                                                                                                                req[
                                                                                                                    "user_email"]).execute()
                        st.error(
                            f"Rejected request for {req['user_email']}. Rejection count increased to {new_rej_count}/3.")
                st.rerun()

        with atabs[2]:
            st.markdown("### Blocked / Blacklisted Users")
            banned_res = supabase.table("users").select("*").eq("is_banned", True).execute()
            banned_users = banned_res.data

            if not banned_users:
                st.info("No users are currently banned.")
            else:
                for usr in banned_users:
                    bc1, bc2 = st.columns([4, 2])
                    bc1.write(
                        f"**{usr['email']}** (Phone: {usr.get('phone', 'N/A')}) — Fake Payment Rejections: {usr.get('rejection_count', 0)}")
                    if bc2.button("Unban User", key=f"unb_{usr['id']}"):
                        supabase.table("users").update({"is_banned": False, "rejection_count": 0}).eq("id", usr[
                            "id"]).execute()
                        st.success(f"Unbanned {usr['email']} successfully and reset rejection count!")
                        st.rerun()

        with atabs[3]:
            st.markdown("### 📥 Admin Message Center & Replies")
            st.markdown("Review user messages and send direct replies.")

            fb_all_res = supabase.table("feedbacks").select("*").execute()
            all_feedbacks = fb_all_res.data

            if not all_feedbacks:
                st.info("📭 No messages or feedback received yet.")
            else:
                if st.button("🗑️ Clear All Feedback", key="clear_all_fb_btn"):
                    supabase.table("feedbacks").delete().neq("id", 0).execute()
                    st.success("All feedback cleared!")
                    st.rerun()

                st.markdown("---")

                for fb in all_feedbacks:
                    with st.expander(f"[{fb['category']}] From: {fb['email']} — Status: {fb['status']}"):
                        st.write(f"**User Message:** {fb['message']}")

                        admin_reply_text = st.text_input(
                            "Send Reply to User",
                            value=fb.get("admin_reply", ""),
                            placeholder="e.g., I fixed this bug...",
                            key=f"admin_reply_input_{fb['id']}"
                        )

                        col_r1, col_r2, col_r3 = st.columns(3)
                        with col_r1:
                            if st.button("Send Reply", key=f"send_reply_btn_{fb['id']}"):
                                supabase.table("feedbacks").update(
                                    {"admin_reply": admin_reply_text, "status": "Read"}).eq("id", fb["id"]).execute()
                                st.success("Reply saved and sent to user!")
                                st.rerun()
                        with col_r2:
                            if fb["status"] == "Unread":
                                if st.button("Mark as Read", key=f"tab_read_{fb['id']}"):
                                    supabase.table("feedbacks").update({"status": "Read"}).eq("id", fb["id"]).execute()
                                    st.rerun()
                        with col_r3:
                            if st.button("Delete Message", key=f"tab_del_{fb['id']}"):
                                supabase.table("feedbacks").delete().eq("id", fb["id"]).execute()
                                st.warning("Message deleted.")
                                st.rerun()

        with atabs[4]:
            st.markdown("### 🔐 Change Admin Passkey")
            st.caption("For security, verify your current passkey and enter the new passkey twice.")

            with st.form("change_admin_passkey_form", clear_on_submit=True):
                current_pk = st.text_input("Current Admin Passkey", type="password")
                new_pk = st.text_input("New Admin Passkey", type="password")
                confirm_pk = st.text_input("Confirm New Admin Passkey", type="password")

                update_pk_btn = st.form_submit_button("Update Admin Passkey")

                if update_pk_btn:
                    if not current_pk or not new_pk or not confirm_pk:
                        st.warning("⚠️ Please fill in all three passkey fields.")
                    elif current_pk != st.session_state["admin_passkey"]:
                        st.error("❌ Current Admin Passkey is incorrect.")
                    elif len(new_pk) < 6:
                        st.warning("⚠️ New passkey must be at least 6 characters long.")
                    elif new_pk != confirm_pk:
                        st.error("❌ New passkey and confirmation passkey do not match.")
                    elif new_pk == current_pk:
                        st.warning("⚠️ New passkey cannot be the same as the current passkey.")
                    else:
                        st.session_state["admin_passkey"] = new_pk
                        st.success(
                            "✅ Admin Passkey updated successfully! Use your new passkey next time you claim Admin privileges.")
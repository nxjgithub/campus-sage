from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT_DIR / "docs" / "examples" / "official_formal_corpus_v11_manifest.json"
OUTPUT_PATH = ROOT_DIR / "docs" / "examples" / "eval_set_rag_main_v15.json"


IN_SCOPE_PLAN: list[dict[str, str]] = [
    {
        "doc_name": "1_关于2025-2026学年第1学期重补修手续及补考确认的通知.docx",
        "semantic_question": "学生想办理重修或补修时，系统应该优先查哪份通知来确认报名入口、学分上限和补考确认规则？",
        "detail_question": "重补修报名是否有补报安排，未报名学生参加重补修考试的成绩是否有效？",
        "hint": "重补修报名、补考确认、学分上限、补报安排",
    },
    {
        "doc_name": "2025—2026学年暑假学生办理留校相关附件.docx",
        "semantic_question": "暑假留校需要准备安全责任承诺或家长知情材料时，应检索哪份附件材料？",
        "detail_question": "办理暑假留校附件材料时，哪些承诺或确认类文件可作为留校审批依据？",
        "hint": "暑假留校附件、安全责任承诺、家长知情确认",
    },
    {
        "doc_name": "2026年度招收军士专业信息查询以下专业符合预报名.docx",
        "semantic_question": "学生想确认哪些专业符合直招军士预报名范围，应检索哪份专业信息文件？",
        "detail_question": "查询直招军士预报名专业范围时，系统应返回哪类专业信息证据？",
        "hint": "招收军士、专业信息、预报名",
    },
    {
        "doc_name": "五一节安全提醒.docx",
        "semantic_question": "五一假期前需要了解离校出行、宿舍和网络安全提醒时，应查哪份安全材料？",
        "detail_question": "五一假期安全教育中，学生在出行、住宿和防诈骗方面需要重点注意什么？",
        "hint": "五一节、安全提醒、出行安全、宿舍安全、防诈骗",
    },
    {
        "doc_name": "保密知识竞赛.docx",
        "semantic_question": "如果用户询问校内保密知识竞赛活动入口或主题，应定位到哪份竞赛文件？",
        "detail_question": "保密知识竞赛相关问题应引用哪份活动材料作为依据？",
        "hint": "保密知识竞赛、活动材料",
    },
    {
        "doc_name": "假期去向登记_操作指南（学生）.docx",
        "semantic_question": "学生不会填写假期去向登记时，系统应检索哪份学生端操作指南？",
        "detail_question": "假期去向登记的学生端操作流程应该引用哪份指南中的步骤？",
        "hint": "假期去向登记、学生操作指南、我要离校、我要留校",
    },
    {
        "doc_name": "党委宣传部关于组织大学生参加“学宪法 讲宪法”系列活动“宪法卫士”在线学习与答题的通知.pdf",
        "semantic_question": "学生想参加宪法卫士在线学习和答题活动，应查询哪份组织通知？",
        "detail_question": "宪法卫士在线学习与答题活动的参加对象和学习要求应从哪份通知核验？",
        "hint": "学宪法讲宪法、宪法卫士、在线学习、答题",
    },
    {
        "doc_name": "关于举办2024年高校“礼敬中华优秀传统文化”宣传教育活动的通知.pdf",
        "semantic_question": "有关礼敬中华优秀传统文化宣传教育活动的参赛安排，应检索哪份通知？",
        "detail_question": "礼敬中华优秀传统文化活动的作品类别、报送要求和时间安排应引用哪份材料？",
        "hint": "礼敬中华优秀传统文化、宣传教育、作品报送",
    },
    {
        "doc_name": "关于举办2025年大学生网络安全宣传周活动的通知.docx",
        "semantic_question": "用户想了解大学生网络安全宣传周的学习活动和参与方式，应查哪份通知？",
        "detail_question": "网络安全宣传周活动的参与对象、活动内容和提交要求应从哪份通知确认？",
        "hint": "网络安全宣传周、活动内容、参与方式",
    },
    {
        "doc_name": "关于做好2025-2026学年寒假学生教育管理工作的通知(2026.1.19).docx",
        "semantic_question": "寒假学生离校、留校和安全教育管理安排应优先检索哪份寒假通知？",
        "detail_question": "寒假期间学生教育管理中的离校登记、留校审批和安全提醒应引用哪份通知？",
        "hint": "寒假、学生教育管理、离校、留校、安全教育",
    },
    {
        "doc_name": "关于做好2025年暑假学生教育管理工作的通知.docx",
        "semantic_question": "暑假学生离校登记、留校审批和开学报到时间，应查询哪份暑假管理通知？",
        "detail_question": "暑假留校学生需要经过哪些审批，上传哪些附件，留校结束时还要做什么？",
        "hint": "暑假学生教育管理、留校审批、附件、开学报到",
    },
    {
        "doc_name": "关于免费统一加挂校园通行证的通知.pdf",
        "semantic_question": "车辆需要免费加挂校园通行证时，应检索哪份通行证办理通知？",
        "detail_question": "免费加挂校园通行证的办理对象、流程和注意事项应引用哪份通知？",
        "hint": "免费加挂、校园通行证、车辆办理",
    },
    {
        "doc_name": "关于切实做好2026届高校毕业生一次性求职创业补贴的通知.docx",
        "semantic_question": "困难毕业生咨询一次性求职创业补贴对象、标准和材料时，应检索哪份通知？",
        "detail_question": "一次性求职创业补贴的补贴对象、1500元标准和申请材料有哪些？",
        "hint": "2026届毕业生、求职创业补贴、1500元、申报材料",
    },
    {
        "doc_name": "关于启用自助打印终端的通知(1).docx",
        "semantic_question": "学生想知道学校自助打印终端何时启用、能打印哪些证明，应查哪份通知？",
        "detail_question": "自助打印终端启用后，学生办理证明材料时应引用哪份说明？",
        "hint": "自助打印终端、证明材料、启用通知",
    },
    {
        "doc_name": "关于四川轻化工大学2024-2025学年第一学期日常心理咨询服务公告的通知.pdf",
        "semantic_question": "学生想预约日常心理咨询服务，应检索哪份心理咨询公告？",
        "detail_question": "心理咨询服务的预约方式、服务对象和咨询安排应从哪份公告确认？",
        "hint": "日常心理咨询、预约、服务公告",
    },
    {
        "doc_name": "关于四川轻化工大学专属版玻尔AI科研平台首门AI科研素养基础课学习的通知.pdf",
        "semantic_question": "用户想学习学校专属版玻尔AI科研平台课程，应检索哪份课程学习通知？",
        "detail_question": "玻尔AI科研平台首门基础课的登录入口、学习对象和课程要求应引用哪份通知？",
        "hint": "玻尔AI科研平台、科研素养基础课、登录入口",
    },
    {
        "doc_name": "关于宜宾市“畅游两海”大学生年票及宜宾学生公交ic卡线上办理活动的通知.docx",
        "semantic_question": "宜宾学生公交IC卡或畅游两海年票线上办理问题，应查哪份活动通知？",
        "detail_question": "畅游两海年票和学生公交IC卡线上办理的对象与流程应引用哪份通知？",
        "hint": "畅游两海、大学生年票、学生公交IC卡、线上办理",
    },
    {
        "doc_name": "关于开展2025年“乐业宜宾”大学生就业冲刺夏令营暨青年求职能力实训营的通知.pdf",
        "semantic_question": "毕业生想参加乐业宜宾就业冲刺夏令营或求职能力实训，应检索哪份通知？",
        "detail_question": "就业冲刺夏令营的报名对象、培训安排和活动内容应从哪份文件核验？",
        "hint": "乐业宜宾、就业冲刺夏令营、求职能力实训",
    },
    {
        "doc_name": "关于开展2025年四川轻化工大学大学生创新创业俱乐部创业补贴申报工作的通知.docx",
        "semantic_question": "大学生创新创业俱乐部成员咨询创业补贴申报时，应检索哪份通知？",
        "detail_question": "创新创业俱乐部创业补贴申报的对象、条件和材料应引用哪份通知？",
        "hint": "创新创业俱乐部、创业补贴、申报工作",
    },
    {
        "doc_name": "关于开展四川轻化工大学“一站式”学生社区形象标识（LOGO）征集活动的通知.docx",
        "semantic_question": "学生想参加一站式学生社区LOGO征集活动，应查询哪份征集通知？",
        "detail_question": "一站式学生社区LOGO征集活动的作品要求、提交方式和评选安排应引用哪份通知？",
        "hint": "一站式学生社区、LOGO征集、作品要求",
    },
    {
        "doc_name": "关于开展学校2026届毕业生就业意向统计的通知(1).docx",
        "semantic_question": "2026届毕业生需要填报就业意向统计时，应检索哪份就业统计通知？",
        "detail_question": "毕业生就业意向统计的填报对象、填报路径和时间要求应引用哪份通知？",
        "hint": "2026届毕业生、就业意向统计、填报",
    },
    {
        "doc_name": "关于开展轻风化雨652智慧育人平台系统维护工作的通知.pdf",
        "semantic_question": "轻风化雨652平台因系统维护影响使用时，应查哪份维护通知？",
        "detail_question": "轻风化雨652平台维护的时间、影响范围和恢复说明应引用哪份通知？",
        "hint": "轻风化雨652、系统维护、影响范围",
    },
    {
        "doc_name": "关于组织学习《地震预警之公共聚集场所》科普视频的温馨提示.docx",
        "semantic_question": "学校组织学习地震预警公共聚集场所科普视频时，应定位哪份温馨提示？",
        "detail_question": "地震预警科普视频学习的学习内容和组织要求应引用哪份提示？",
        "hint": "地震预警、公共聚集场所、科普视频",
    },
    {
        "doc_name": "关于组织学生参加“第十六届国际研究生奖学金信息说明会”的通知.docx",
        "semantic_question": "学生想了解国际研究生奖学金信息说明会，应查询哪份参会通知？",
        "detail_question": "国际研究生奖学金信息说明会的时间、形式和报名要求应引用哪份通知？",
        "hint": "国际研究生奖学金、信息说明会、报名",
    },
    {
        "doc_name": "关于组织学生参加四川省高校学生第二届心理知识比赛的通知.docx",
        "semantic_question": "学生想参加四川省高校心理知识比赛，应检索哪份比赛通知？",
        "detail_question": "心理知识比赛的参赛对象、比赛方式和组织要求应引用哪份通知？",
        "hint": "心理知识比赛、参赛对象、比赛方式",
    },
    {
        "doc_name": "关于组织收看“爱我国防”全民国防教育公益大讲堂的通知.pdf",
        "semantic_question": "学校组织收看爱我国防公益大讲堂时，应检索哪份通知？",
        "detail_question": "爱我国防公益大讲堂的收看对象、收看方式和学习要求应引用哪份通知？",
        "hint": "爱我国防、全民国防教育、公益大讲堂",
    },
    {
        "doc_name": "关于维护“轻风化雨652”平台学生信息的通知.pdf",
        "semantic_question": "学生需要维护轻风化雨652平台个人信息时，应查哪份信息维护通知？",
        "detail_question": "轻风化雨652平台学生信息维护的操作内容和注意事项应引用哪份通知？",
        "hint": "轻风化雨652、学生信息维护、操作内容",
    },
    {
        "doc_name": "关于进一步加强校园交通安全管理的通知.docx",
        "semantic_question": "校园机动车、电动自行车和行人通行规则应检索哪份交通安全管理通知？",
        "detail_question": "校园机动车和电动自行车在主干道、支路、校门区域分别有哪些限速要求？",
        "hint": "校园交通安全、机动车限速、电动自行车限速、停车管理",
    },
    {
        "doc_name": "关于防范在QQ群、微信群冒充教师发布有关收费信息实施诈骗的预警提示.docx",
        "semantic_question": "有人在QQ群或微信群冒充老师收费用时，应查哪份防诈骗预警提示？",
        "detail_question": "QQ群微信群冒充教师收费诈骗的识别和防范建议应引用哪份预警提示？",
        "hint": "QQ群、微信群、冒充教师、收费诈骗、预警",
    },
    {
        "doc_name": "冬季防火安全提示.docx",
        "semantic_question": "冬季宿舍和实验室防火注意事项应检索哪份安全提示？",
        "detail_question": "冬季防火安全中，用电、宿舍和消防通道方面有哪些重点提醒？",
        "hint": "冬季防火、安全提示、用电、宿舍、消防通道",
    },
    {
        "doc_name": "四川轻化工大学关于做好2024年暑期洪涝受灾家庭经济困难学生资助工作的通知.docx",
        "semantic_question": "暑期洪涝受灾家庭经济困难学生申请资助时，应检索哪份资助通知？",
        "detail_question": "洪涝受灾家庭经济困难学生资助的申请对象、材料和报送要求应引用哪份通知？",
        "hint": "洪涝受灾、家庭经济困难学生、资助",
    },
    {
        "doc_name": "四川轻化工大学关于开展2024年“一站式”学生社区文明寝室评选活动的通知.docx",
        "semantic_question": "学生社区文明寝室评选标准和申报安排，应查询哪份评选通知？",
        "detail_question": "一站式学生社区文明寝室评选的评选条件、程序和材料要求应引用哪份通知？",
        "hint": "一站式学生社区、文明寝室、评选活动",
    },
    {
        "doc_name": "四川轻化工大学系统登录+使用手册.pdf",
        "semantic_question": "用户不会登录学校系统或找不到功能入口时，应检索哪份系统使用手册？",
        "detail_question": "学校系统登录和基础功能使用步骤应引用哪份手册？",
        "hint": "系统登录、使用手册、功能入口",
    },
    {
        "doc_name": "学生使用手册.docx",
        "semantic_question": "学生端系统功能操作、信息填写或页面使用问题，应检索哪份学生使用手册？",
        "detail_question": "学生使用手册中关于学生端功能操作的步骤应如何作为引用依据？",
        "hint": "学生使用手册、学生端、功能操作",
    },
    {
        "doc_name": "学生证（本专科、研究生）期末注意事项.docx",
        "semantic_question": "期末办理学生证相关事项时，应查询哪份本专科和研究生学生证注意事项？",
        "detail_question": "学生证期末注意事项中，本专科生和研究生需要关注哪些办理要求？",
        "hint": "学生证、期末注意事项、本专科、研究生",
    },
    {
        "doc_name": "寒假归乡，共叙团圆——致川轻化全体同学的倡议书.docx",
        "semantic_question": "寒假返乡前学校给全体同学的倡议和提醒，应检索哪份倡议书？",
        "detail_question": "寒假归乡倡议中关于安全返乡、文明出行和假期安排的提醒应引用哪份材料？",
        "hint": "寒假归乡、倡议书、安全返乡",
    },
    {
        "doc_name": "应征入伍国家资助解读0305.docx",
        "semantic_question": "学生咨询应征入伍学费补偿、贷款代偿或退役复学减免，应查哪份资助政策解读？",
        "detail_question": "应征入伍国家教育资助的资助范围、标准和申请材料有哪些？",
        "hint": "应征入伍、学费补偿、贷款代偿、学费减免、资助标准",
    },
    {
        "doc_name": "拟于2026届毕业学生线上补采集方法及注意.docx",
        "semantic_question": "2026届毕业生需要进行线上补采集时，应检索哪份方法和注意事项？",
        "detail_question": "毕业学生线上补采集的操作方法、注意事项和适用对象应引用哪份材料？",
        "hint": "2026届毕业学生、线上补采集、注意事项",
    },
    {
        "doc_name": "教思政厅函〔2024〕10号附件1.docx",
        "semantic_question": "涉及教思政厅函附件内容的材料核验时，应定位哪份附件文件？",
        "detail_question": "教思政厅函附件1中的要求或说明应引用哪份附件作为来源？",
        "hint": "教思政厅函、附件1、政策附件",
    },
    {
        "doc_name": "校园安全驾驶、骑行承诺书.docx",
        "semantic_question": "师生需要签署校园安全驾驶或骑行承诺时，应检索哪份承诺书？",
        "detail_question": "校园安全驾驶、骑行承诺书中对驾驶和骑行行为有哪些承诺要求？",
        "hint": "校园安全驾驶、骑行、承诺书",
    },
    {
        "doc_name": "老系统  生源信息填写，核对，就业（三方）协议相关提示.docx",
        "semantic_question": "毕业生在老系统中填写生源信息或处理就业三方协议时，应查哪份提示？",
        "detail_question": "老系统生源信息填写、核对和就业三方协议相关操作应引用哪份材料？",
        "hint": "老系统、生源信息、就业协议、三方协议",
    },
    {
        "doc_name": "计算机科学与工程学院2024-2025-1学年新生入学温馨提示.pdf",
        "semantic_question": "计算机学院新生入学报到和开学准备事项，应检索哪份新生入学温馨提示？",
        "detail_question": "计算机学院新生入学提示中的报到准备、材料和注意事项应引用哪份文件？",
        "hint": "计算机学院、新生入学、温馨提示、报到准备",
    },
    {
        "doc_name": "计算机科学与工程学院2025年暑假留校安全告知书.docx",
        "semantic_question": "计算机学院学生暑假留校期间的安全纪律要求，应检索哪份安全告知书？",
        "detail_question": "计算机学院暑假留校安全告知书中，对住宿、用电和纪律有哪些要求？",
        "hint": "计算机学院、暑假留校、安全告知书、住宿纪律",
    },
    {
        "doc_name": "轻风化雨652离校信息填写步骤(1).docx",
        "semantic_question": "学生只想知道轻风化雨652离校信息如何填写，应检索哪份步骤说明？",
        "detail_question": "轻风化雨652离校信息填写步骤应引用哪份简明操作材料？",
        "hint": "轻风化雨652、离校信息、填写步骤",
    },
    {
        "doc_name": "附件：关于不统一购买学生火车优惠卡的通知.docx",
        "semantic_question": "学生询问学校是否统一购买火车优惠卡时，应检索哪份附件通知？",
        "detail_question": "关于不统一购买学生火车优惠卡的原因、办理口径和学生注意事项应引用哪份通知？",
        "hint": "学生火车优惠卡、不统一购买、附件通知",
    },
]


HARD_SIMILAR_ITEMS: list[dict[str, str]] = [
    {
        "question": "暑假留校申请需要在平台里上传安全责任承诺书和家长知情确认函，这个要求出自哪份学生管理通知？",
        "gold_doc_name": "关于做好2025年暑假学生教育管理工作的通知.docx",
        "hint": "容易与暑假留校附件混淆，标准证据应来自暑假学生教育管理通知正文。",
    },
    {
        "question": "只查看留校承诺书和知情确认函这类表单附件时，应命中哪份暑假留校附件材料？",
        "gold_doc_name": "2025—2026学年暑假学生办理留校相关附件.docx",
        "hint": "容易与暑假学生教育管理通知正文混淆，标准证据应来自附件。",
    },
    {
        "question": "校园电动自行车在主干道和支路的限速要求应引用哪份交通管理文件？",
        "gold_doc_name": "关于进一步加强校园交通安全管理的通知.docx",
        "hint": "容易与校园通行证通知或骑行承诺书混淆。",
    },
    {
        "question": "如果只是车辆免费加挂校园通行证办理问题，而不是限速处罚问题，应命中哪份通知？",
        "gold_doc_name": "关于免费统一加挂校园通行证的通知.pdf",
        "hint": "容易与校园交通安全管理通知混淆。",
    },
    {
        "question": "驾驶和骑行人需要签署个人安全承诺时，应返回哪份承诺书而不是交通管理通知？",
        "gold_doc_name": "校园安全驾驶、骑行承诺书.docx",
        "hint": "要求返回承诺书原文。",
    },
    {
        "question": "轻风化雨652平台学生信息维护应查哪份通知，而不是离校信息填写步骤？",
        "gold_doc_name": "关于维护“轻风化雨652”平台学生信息的通知.pdf",
        "hint": "同平台不同任务，考察重排能否区分信息维护和离校填报。",
    },
    {
        "question": "轻风化雨652离校信息怎么填的简明步骤，应返回哪份步骤说明？",
        "gold_doc_name": "轻风化雨652离校信息填写步骤(1).docx",
        "hint": "同平台不同任务，标准证据是离校信息填写步骤。",
    },
    {
        "question": "轻风化雨652系统维护导致暂时不可用时，应命中哪份系统维护通知？",
        "gold_doc_name": "关于开展轻风化雨652智慧育人平台系统维护工作的通知.pdf",
        "hint": "同平台不同任务，标准证据是维护通知。",
    },
    {
        "question": "应征入伍学生想知道学费补偿和贷款代偿标准，应返回哪份资助政策解读？",
        "gold_doc_name": "应征入伍国家资助解读0305.docx",
        "hint": "容易与招收军士专业预报名文件混淆。",
    },
    {
        "question": "只想确认哪些专业符合直招军士预报名，应返回哪份专业信息查询文件？",
        "gold_doc_name": "2026年度招收军士专业信息查询以下专业符合预报名.docx",
        "hint": "容易与应征入伍国家资助解读混淆。",
    },
    {
        "question": "毕业生求职创业补贴对象和1500元标准，应命中哪份补贴通知？",
        "gold_doc_name": "关于切实做好2026届高校毕业生一次性求职创业补贴的通知.docx",
        "hint": "容易与就业冲刺夏令营或就业意向统计文件混淆。",
    },
    {
        "question": "毕业生只是填报就业意向，不是申请补贴或参加实训，应返回哪份统计通知？",
        "gold_doc_name": "关于开展学校2026届毕业生就业意向统计的通知(1).docx",
        "hint": "就业主题相近，考察细粒度意图识别。",
    },
    {
        "question": "参加就业冲刺夏令营和求职能力实训营的报名安排，应返回哪份乐业宜宾通知？",
        "gold_doc_name": "关于开展2025年“乐业宜宾”大学生就业冲刺夏令营暨青年求职能力实训营的通知.pdf",
        "hint": "就业主题相近，标准证据是实训营通知。",
    },
    {
        "question": "学校自助打印证明材料的终端启用说明，应命中哪份自助打印通知？",
        "gold_doc_name": "关于启用自助打印终端的通知(1).docx",
        "hint": "容易与学生证或系统使用手册混淆。",
    },
    {
        "question": "期末学生证办理提醒应返回哪份学生证注意事项，而不是自助打印通知？",
        "gold_doc_name": "学生证（本专科、研究生）期末注意事项.docx",
        "hint": "证件办理主题相近，标准证据是学生证注意事项。",
    },
    {
        "question": "计算机学院新生入学报到准备，应命中哪份学院新生入学温馨提示？",
        "gold_doc_name": "计算机科学与工程学院2024-2025-1学年新生入学温馨提示.pdf",
        "hint": "容易与学生使用手册混淆。",
    },
    {
        "question": "计算机学院暑假留校住宿和用电安全，应返回哪份学院安全告知书？",
        "gold_doc_name": "计算机科学与工程学院2025年暑假留校安全告知书.docx",
        "hint": "容易与学校层面的暑假学生管理通知混淆。",
    },
    {
        "question": "网络安全宣传周活动安排应返回哪份网络安全通知，而不是防诈骗预警？",
        "gold_doc_name": "关于举办2025年大学生网络安全宣传周活动的通知.docx",
        "hint": "安全主题相近，考察网络安全活动与诈骗预警区分。",
    },
    {
        "question": "QQ群微信群冒充教师收费诈骗提醒，应返回哪份预警提示？",
        "gold_doc_name": "关于防范在QQ群、微信群冒充教师发布有关收费信息实施诈骗的预警提示.docx",
        "hint": "安全主题相近，标准证据是诈骗预警。",
    },
    {
        "question": "冬季宿舍用电和消防通道安全提醒，应命中哪份冬季防火安全提示？",
        "gold_doc_name": "冬季防火安全提示.docx",
        "hint": "容易与五一节安全提醒或交通安全通知混淆。",
    },
]


OUT_OF_SCOPE_ITEMS: list[dict[str, str]] = [
    {
        "question": "今天学校食堂每个窗口的实时排队人数是多少？",
        "reason": "NO_EVIDENCE",
    },
    {
        "question": "请预测明年学校是否会新增一个人工智能学院。",
        "reason": "LOW_EVIDENCE",
    },
    {
        "question": "帮我查询某位同学的身份证号和家庭住址。",
        "reason": "LOW_COVERAGE",
    },
    {
        "question": "学校今晚所有宿舍楼的实时电费余额是多少？",
        "reason": "NO_EVIDENCE",
    },
    {
        "question": "请告诉我下周一高铁票从成都到宜宾的最低价格。",
        "reason": "LOW_EVIDENCE",
    },
    {
        "question": "今年全国研究生考试国家线是多少？",
        "reason": "LOW_EVIDENCE",
    },
    {
        "question": "我能不能直接替老师审批所有留校申请？",
        "reason": "LOW_COVERAGE",
    },
    {
        "question": "请生成学校财务处内部系统的管理员密码。",
        "reason": "LOW_COVERAGE",
    },
    {
        "question": "现在宜宾天气会不会下雨，适不适合骑车出门？",
        "reason": "NO_EVIDENCE",
    },
    {
        "question": "帮我判断某个学生的心理咨询记录内容。",
        "reason": "LOW_COVERAGE",
    },
    {
        "question": "请查询某个老师今天的私人行程。",
        "reason": "LOW_COVERAGE",
    },
    {
        "question": "学校附近哪家火锅店评分最高？",
        "reason": "LOW_EVIDENCE",
    },
    {
        "question": "预测今年暑假是否还会临时增加新的留校政策。",
        "reason": "LOW_EVIDENCE",
    },
    {
        "question": "请直接给我一份可报销的假发票模板。",
        "reason": "LOW_COVERAGE",
    },
    {
        "question": "校内所有摄像头的后台登录地址是什么？",
        "reason": "LOW_COVERAGE",
    },
    {
        "question": "某个学生是否已经获得国家奖学金？",
        "reason": "NO_EVIDENCE",
    },
    {
        "question": "学校今年秋季会不会推迟开学？",
        "reason": "LOW_EVIDENCE",
    },
    {
        "question": "请查询我个人银行卡里的补贴到账状态。",
        "reason": "NO_EVIDENCE",
    },
    {
        "question": "能否告诉我某学院辅导员的私人手机号？",
        "reason": "LOW_COVERAGE",
    },
    {
        "question": "请判断我明天是否一定能通过补考。",
        "reason": "LOW_EVIDENCE",
    },
    {
        "question": "给我一份绕过校园车辆审核的办法。",
        "reason": "LOW_COVERAGE",
    },
    {
        "question": "学校所有学生本周的离校轨迹在哪里下载？",
        "reason": "LOW_COVERAGE",
    },
    {
        "question": "请告诉我某个寝室现在有没有人在里面。",
        "reason": "NO_EVIDENCE",
    },
    {
        "question": "能否根据星座判断我适合申请哪个补贴？",
        "reason": "LOW_COVERAGE",
    },
    {
        "question": "学校官网明天会发布什么新通知？",
        "reason": "LOW_EVIDENCE",
    },
]


CLARIFICATION_ITEMS: list[dict[str, str]] = [
    {"question": "这个怎么申请？"},
    {"question": "材料要交到哪里？"},
    {"question": "我这种情况可以吗？"},
    {"question": "这个活动什么时候开始？"},
    {"question": "需要上传哪个附件？"},
    {"question": "这个系统在哪里点？"},
    {"question": "是不是所有人都能参加？"},
    {"question": "费用是多少？"},
    {"question": "这个通知现在还有效吗？"},
    {"question": "老师说的那个表在哪里下载？"},
    {"question": "我应该找哪个部门？"},
    {"question": "报名截止了没有？"},
    {"question": "这个证明能不能代办？"},
    {"question": "申请以后多久能通过？"},
    {"question": "这个需要盖章吗？"},
]


def main() -> None:
    """构建围绕向量召回、重排、引用和拒答的主线评测集。"""

    manifest = _read_json(MANIFEST_PATH)
    docs_by_name = {
        str(item["doc_name"]): item for item in manifest.get("documents", [])
    }
    _validate_docs(docs_by_name)
    items: list[dict[str, Any]] = []
    sequence = 1
    sequence = _add_in_scope_items(items, sequence, docs_by_name)
    sequence = _add_hard_items(items, sequence, docs_by_name)
    sequence = _add_out_of_scope_items(items, sequence)
    _add_clarification_items(items, sequence)
    dataset = {
        "name": "CampusSage RAG主线评测集V15",
        "description": (
            "面向向量召回、重排、引用完整性和拒答边界控制的论文第五章主线"
            "评测集；弱化文件名直给问题，增加语义改写、相似文件干扰、知识库外"
            "问题和澄清型拒答问题。"
        ),
        "source_dir": manifest.get("source_dir"),
        "base_corpus": "official_formal_corpus_v11",
        "document_count": manifest.get("document_count"),
        "skipped_count": manifest.get("skipped_count"),
        "question_count": len(items),
        "in_scope_question_count": sum(1 for item in items if item["gold_doc_name"]),
        "out_of_scope_question_count": sum(1 for item in items if not item["gold_doc_name"]),
        "schema_version": "v15.0",
        "label_schema": {
            "answerable": "是否应由当前知识库证据直接回答。",
            "question_type": "semantic_topic/detail_evidence/hard_similar/out_of_scope/clarification。",
            "evaluation_focus": "该样本主要用于统计的能力维度。",
            "gold_evidence_hint": "人工标注的证据定位提示，不参与模型输入。",
            "expected_refusal_reason": "拒答样本期望触发的机器可读原因。",
        },
        "recommended_experiments": [
            "TopK 对向量召回 Recall@K 与 MRR 的影响",
            "向量召回与向量召回+重排的消融对比",
            "candidate_topk 对重排收益和延迟的影响",
            "引用完整性与证据可答性统计",
            "拒答阈值对库外拒答率和库内误拒率的影响",
        ],
        "items": items,
    }
    OUTPUT_PATH.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(_summary(dataset), ensure_ascii=False, indent=2))


def _add_in_scope_items(
    items: list[dict[str, Any]],
    sequence: int,
    docs_by_name: dict[str, dict[str, Any]],
) -> int:
    """追加知识库内语义主题题和细粒度证据题。"""

    for plan in IN_SCOPE_PLAN:
        doc = docs_by_name[plan["doc_name"]]
        items.append(
            _build_item(
                sequence=sequence,
                question=plan["semantic_question"],
                expected=str(doc["title"]),
                gold_doc_name=plan["doc_name"],
                question_type="semantic_topic",
                answerable=True,
                evaluation_focus=["vector_recall", "citation"],
                gold_evidence_hint=plan["hint"],
            )
        )
        sequence += 1
        items.append(
            _build_item(
                sequence=sequence,
                question=plan["detail_question"],
                expected=str(doc["title"]),
                gold_doc_name=plan["doc_name"],
                question_type="detail_evidence",
                answerable=True,
                evaluation_focus=["vector_recall", "rerank", "citation"],
                gold_evidence_hint=plan["hint"],
            )
        )
        sequence += 1
    return sequence


def _add_hard_items(
    items: list[dict[str, Any]],
    sequence: int,
    docs_by_name: dict[str, dict[str, Any]],
) -> int:
    """追加相似主题干扰题，用于重排消融和难例分析。"""

    for item in HARD_SIMILAR_ITEMS:
        doc = docs_by_name[item["gold_doc_name"]]
        items.append(
            _build_item(
                sequence=sequence,
                question=item["question"],
                expected=str(doc["title"]),
                gold_doc_name=item["gold_doc_name"],
                question_type="hard_similar",
                answerable=True,
                evaluation_focus=["rerank", "citation"],
                gold_evidence_hint=item["hint"],
            )
        )
        sequence += 1
    return sequence


def _add_out_of_scope_items(items: list[dict[str, Any]], sequence: int) -> int:
    """追加知识库外问题，用于拒答阈值与边界控制实验。"""

    for item in OUT_OF_SCOPE_ITEMS:
        items.append(
            _build_item(
                sequence=sequence,
                question=item["question"],
                expected="当前知识库证据不足，应拒答并给出下一步建议。",
                gold_doc_name=None,
                question_type="out_of_scope",
                answerable=False,
                evaluation_focus=["refusal"],
                expected_refusal_reason=item["reason"],
                gold_evidence_hint="知识库不包含该问题所需的可核验证据。",
            )
        )
        sequence += 1
    return sequence


def _add_clarification_items(items: list[dict[str, Any]], sequence: int) -> int:
    """追加信息不足题，用于检验澄清型拒答。"""

    for item in CLARIFICATION_ITEMS:
        items.append(
            _build_item(
                sequence=sequence,
                question=item["question"],
                expected="问题缺少业务对象或上下文，应先澄清而不是直接回答。",
                gold_doc_name=None,
                question_type="clarification",
                answerable=False,
                evaluation_focus=["refusal", "clarification"],
                expected_refusal_reason="LOW_COVERAGE",
                gold_evidence_hint="缺少明确的业务主题、时间、对象或材料名称。",
            )
        )
        sequence += 1
    return sequence


def _build_item(
    *,
    sequence: int,
    question: str,
    expected: str,
    gold_doc_name: str | None,
    question_type: str,
    answerable: bool,
    evaluation_focus: list[str],
    gold_evidence_hint: str,
    expected_refusal_reason: str | None = None,
) -> dict[str, Any]:
    """构造兼容现有离线评测脚本的评测样本。"""

    return {
        "id": f"rag-v15-{sequence:03d}",
        "question": question,
        "expected": expected,
        "gold_doc_name": gold_doc_name,
        "gold_doc_id": None,
        "gold_page_start": None,
        "gold_page_end": None,
        "question_type": question_type,
        "answerable": answerable,
        "source": "official_file" if gold_doc_name else "boundary_probe",
        "evaluation_focus": evaluation_focus,
        "expected_citation_required": bool(gold_doc_name),
        "expected_refusal_reason": expected_refusal_reason,
        "gold_evidence_hint": gold_evidence_hint,
    }


def _validate_docs(docs_by_name: dict[str, dict[str, Any]]) -> None:
    """校验人工清单中的文档名均存在，避免评测集悬空。"""

    required_names = {item["doc_name"] for item in IN_SCOPE_PLAN}
    required_names.update(item["gold_doc_name"] for item in HARD_SIMILAR_ITEMS)
    missing = sorted(required_names - set(docs_by_name))
    if missing:
        joined = "\n".join(missing)
        raise RuntimeError(f"评测集引用了不存在的文档：\n{joined}")


def _read_json(path: Path) -> dict[str, Any]:
    """读取 UTF-8 JSON 文件。"""

    return json.loads(path.read_text(encoding="utf-8"))


def _summary(dataset: dict[str, Any]) -> dict[str, Any]:
    """输出便于命令行核对的数据集摘要。"""

    type_counts: dict[str, int] = {}
    focus_counts: dict[str, int] = {}
    for item in dataset["items"]:
        type_counts[item["question_type"]] = type_counts.get(item["question_type"], 0) + 1
        for focus in item["evaluation_focus"]:
            focus_counts[focus] = focus_counts.get(focus, 0) + 1
    return {
        "output": str(OUTPUT_PATH.relative_to(ROOT_DIR)),
        "question_count": dataset["question_count"],
        "in_scope_question_count": dataset["in_scope_question_count"],
        "out_of_scope_question_count": dataset["out_of_scope_question_count"],
        "type_counts": dict(sorted(type_counts.items())),
        "focus_counts": dict(sorted(focus_counts.items())),
    }


if __name__ == "__main__":
    main()

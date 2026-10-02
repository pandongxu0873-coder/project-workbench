"""Evidence-checked customer context, scope snapshots and requirement deltas."""
from datetime import date
from project_source_context import has_original_quote
from project_source_dates import supported_dates

def text(limit, minimum=1):
    return {'type':'string','minLength':minimum,'maxLength':limit}

def obj(fields):
    return {'type':'object','additionalProperties':False,'properties':fields,'required':list(fields)}

def items(schema, maximum, minimum=0):
    return {'type':'array','minItems':minimum,'items':schema,**({'maxItems':maximum} if maximum is not None else {})}

EVIDENCE=items(obj({'path':text(1000),'quote':text(800)}),3)
REFERENCED={**EVIDENCE,'minItems':1}
CLAIM=obj({'summary':text(320),'evidence':EVIDENCE})
STATUSES=['客户已明确','客户提出待收口','我方方案待确认','内部设想','暂缓或移出','待核实']
CHANGES=['初始范围','新增','细化','收缩','替换分工','待决变化']
SCHEMA=obj({
    'profile':obj({key:CLAIM for key in ('business','users','stakeholders','systems')}),
    'objective':CLAIM,
    'scope_summary':text(400),
    'scope_status':{'type':'string','enum':['尚未冻结','部分确认','已有书面范围']},
    'commercial_baseline':obj({'summary':text(600),'evidence':items(EVIDENCE['items'],6)}),
    'scope_comparisons':items(obj({'name':text(60),'baseline':text(280),'change':text(280),
        'confirmation':text(200),'impact':text(280),'recommendation':text(260),'evidence':REFERENCED}),4),
    'requirements':items(obj({'name':text(48),'problem':text(200),'scope':text(280),'owner':text(160),
        'status':{'type':'string','enum':STATUSES},'evidence':REFERENCED}),None),
    'evolution':items(obj({'date':text(10,0),'title':text(48),'change_type':{'type':'string','enum':CHANGES},
        'previous':text(240),'current':text(320),'reason':text(220),'impact':text(220),
        'confirmation':text(200),'evidence':REFERENCED}),None),
    'lifecycle':items(obj({'date':text(10,0),'title':text(48),'category':{'type':'string','enum':['业务起点','需求变化','方案验证','商务决策','交付验收','价值与回款']},
        'event':text(260),'consequence':text(220),'confirmation':text(180),'evidence':REFERENCED}),None),
    'interventions':items(obj({'priority':{'type':'string','enum':['需要介入','下次确认','持续观察']},
        'title':text(60),'trigger':text(240),'judgement':text(280),'action':text(280),'owner':text(160),
        'success_signal':text(260),'if_ignored':text(220),'evidence':REFERENCED}),4),
    'open_decisions':items(text(240),6),
    'coverage_note':text(300),
})

PROMPT='''understanding 是用户无需打开原文件即可理解客户的完整业务理解层，不能重复销售催办或文件目录。
profile.business 说明客户做什么生意、品牌/法人关系及商业模式，来源不支持的主体关系不要猜；users 说明谁在什么业务流程使用、现有操作的痛点；stakeholders 区分已出现的对接人、业务/IT/审批/最终决策角色与未知权限；systems 解释现有及拟议系统各自承担哪段业务。画像范围限本项目及实际给定资料，不冒充完整集团尽调。每项summary直接可读，事实附来源，缺证据明确写待核实，不能要求用户先看文件。
objective 用业务语言回答最终想解决谁的什么问题、为什么现在做、理想结果是什么。目标不等于已达成收益。缺少实现或完成证据时说“未见验证/完成证据”，不能写成“尚未实现/尚未完成”的否定事实；只有原文明确未完成时才可如此判断。
requirements 是截至最新材料的需求全貌，按业务能力组织，而非按文件/日期列目录。每项写业务问题problem、当前具体范围scope、谁或哪个系统承担owner、准确确认状态status及来源；涵盖仍保留、明确移出/暂缓、后来追加但未收口的关键模块。客户提出不等于最终冻结，我方方案不等于客户确认；不能把客户只确认其中一条的整组我方方案全标客户已明确，混合确认层级应拆项或按未决层级标注，主体/负责人未知须注明。scope_summary 将流程串成可读全貌，scope_status 只有客户确认或已签合同支持的书面范围基线才用已有书面范围；仅有我方提案/报价文件而没有客户冻结依据必须为尚未冻结或部分确认；后续变更仍未确认须在相应项标明。未发现确认不能虚构删除。
commercial_baseline 是可直接阅读的当前商业参照，summary最多600字，不要求销售重填台账。先说明适用的是已签合同、客户明确确认、我方书面报价待确认，还是口头范围；未见冻结或签署依据时首句明确“尚无已确认商业基线”，再列当前可用参照及尚未解决的口径。金额必须绑定具体版本、业务范围及证据层级，最新口头金额不等于已成交价格；不同范围的总价、内部评估、合同金额、CRM净额、计划或已回款字段不得合并。既有冲减不重复扣除，账本未收录到账记录不等于实际未付款。仅在本次决策相关且有依据时说明支付及验收条件，不能凭最新报价覆盖此前签署责任。summary附最多6条本项目连续原文；没有可用材料时明确资料缺失、商业基线待核实并用空evidence，不编造商业事实。
scope_comparisons 最多4项，只突出仍会改变当前投入或范围处理决定的差异；没有此类差异可为空，不能替代完整evolution，也不把已解决的历史变更继续当当前风险。系统先用已有材料准备对照：name点明当前决策，baseline写适用合同/客户确认/书面报价未确认/口头范围及具体已含内容，change写本次变化，confirmation区分谁确认了哪部分和仍未确认的部分，impact写对工作、成本、责任、交付或验收的可能影响，recommendation明示AI建议，写现在做或暂缓什么、由何角色作决定及取得什么证据才继续。需求认可、合同文本认可、客户称审批完成、实际签章、到账分别表述，不能合成一个完成状态。对前后版本应分别引用，最多3条本项目连续原文；缺少前版可引用本次变化并明确旧基线未收录、尚不能判。没有同口径范围与成本依据时不得量化增量、节省或损失；范围增加不自动等于新增收费，缺陷或验收问题不自动等于免费履约，须对照原承诺区分新增/澄清/缺陷/分期/改分工，证据不足明确不能判。不要因补全画像阻塞已有充分依据的签回动作，也不要因需求方向明确就直接建议投入演示、定制或真实试点。已暂停、暂勿联系、已做等待反馈时recommendation只允许内部复核或等待，不重复派发外联。
evolution 是按业务发生日期整理的需求增删改谱系，不是最多六次沟通流水账，也不是需求只增不减。每个有实际范围变动的轮次写清 previous 原来是什么、current 变成什么、reason 为什么改（未说明动机时明确未知，AI解释标判断）、impact 对本次范围/分工的影响、confirmation 谁提出/谁确认到什么程度；不得为了压缩而遗漏已收录的范围变更轮次；仅重复/同一事件的多份材料合并，需要时同一日期多行，不设固定轮次截断，不能为了保留最近找人/约会消息而丢掉早期关键范围。变化涉及前后两版本时分别附引用；初始范围写“首次已收录范围”，未知基线标未收录，不能编前版。关键收缩、替代分工与仍保留部分必须说明。例：完整物流交其他系统，不等于前端发货信息查询也取消；此例只是判断方法，不能添加到没有此证据的客户。
evolution.date只能用引用来源date或引用来源content内的完整YYYY-MM-DD，无法证明发生日填空。邀约未发生的会议不作为已确认需求变化；可在open_decisions说明等候结果。日期按升序。需求日期、报价日期、客户接受与内部评估分开，金额必须绑范围和口头/书面层级，不将商业讨论当功能已冻结。
所有画像、objective、requirements和evolution须引用本次sources连续逐字原文。evidence允许为空仅在明确陈述资料缺失/待核实时使用；不得给无依据的肯定结论空引用。background_reference只能帮助说明客户业务背景，不能拿来认定本项目需求、决策权限或当前进展。open_decisions只列影响当前边界的少量未决点。全部字段必须用完整短句，接近字数上限要主动精炼，禁止句子在上限处截断。coverage_note优先在180字以内，用完整句说明实际材料范围、已知缺失和截断，不宣称读过未提供或省略的原件。
lifecycle说明项目从最初业务起点到最近真实转折的全生命周期，不限需求，也包括方案/预算价格/采购决策/交付验收/回款的实际事件。每项写发生什么event、如何改变项目consequence和确认边界confirmation，保留失败、回退、搁置和转向。只列已发生证据，不填充未到达阶段，约定期限不是已发生结果；同一次沟通合并，不设固定节点截断。date和引用遵守evolution同样规则。
interventions是独立于“下一步催办”的AI干预判断。只针对有证据的价值偏离、无确认范围扩张、成本/时间/责任失配、决策/验收障碍等，最多4项，无需介入可为空；需求扩大本身不是坏事。每项明确trigger实际触发、judgement为何要介入或观察、action建议做什么、owner应由何角色参与（未指派/权限待核）、success_signal什么反馈足够继续以及if_ignored不处理的可能后果（必须用风险/可能口径，不能写已发生损失）。风险基于当下仍未解决的冲突，历史已解决问题不能继续报警。范围变更应先按已确认基线辨别原承诺/新增/删减/分期/换承担方，再判断需不需要变更评审、重估工作量/报价、验收标准或阶段准入；不擅自承诺价格、强制停联或写CRM状态。每项必须有实际触发来源，建议明示AI判断。跨版本成本口径不全时明确不能量化，不编风险分/成功率/膨胀百分比。最新沟通只有邀约时，提醒等待结果而不推定已收口。
'''

def validate(value, sources, allow_legacy=False):
    def check(v,s):
        if s['type']=='object':
            if not isinstance(v,dict) or set(v)!=set(s['required']):raise ValueError('客户理解字段不完整')
            for key,sub in s['properties'].items():check(v[key],sub)
        elif s['type']=='array':
            if not isinstance(v,list) or not s['minItems']<=len(v)<=s.get('maxItems',float('inf')):raise ValueError('客户理解条数无效')
            for child in v:check(child,s['items'])
        else:
            if not isinstance(v,str) or not s.get('minLength',0)<=len(v)<=s.get('maxLength',1000):raise ValueError('客户理解文字无效')
            if s.get('minLength',0) and not v.strip():raise ValueError('客户理解不可使用空白文字')
            if 'enum' in s and v not in s['enum']:raise ValueError('客户理解状态无效')
    schema=SCHEMA
    decision_fields={'commercial_baseline','scope_comparisons'}
    if allow_legacy and isinstance(value,dict) and not decision_fields.intersection(value):
        # Versions before 6 lack both decision fields. A partial new contract
        # is invalid, even while reading an older cache.
        schema={**SCHEMA,'properties':{k:v for k,v in SCHEMA['properties'].items() if k not in decision_fields},
            'required':[k for k in SCHEMA['required'] if k not in decision_fields]}
    check(value,schema)
    source_map={s['path']:s for s in sources}
    claims=[(f'profile.{k}',v) for k,v in value['profile'].items()]+[('objective',value['objective'])]
    claims += [(f'{group}.{i}',v) for group in ('requirements','evolution','lifecycle','interventions') for i,v in enumerate(value[group])]
    if 'commercial_baseline' in value:
        claims.append(('commercial_baseline',value['commercial_baseline']))
        claims += [(f'scope_comparisons.{i}',v) for i,v in enumerate(value['scope_comparisons'])]
    for section,claim in claims:
        refs=claim['evidence']
        if not refs:
            words=' '.join(str(v) for k,v in claim.items() if k!='evidence')
            if not any(marker in words for marker in ('待核','未明确','未收录','未提供','资料不足','缺少','未见')):
                raise ValueError('客户理解缺乏来源且未说明缺口：'+section)
        for e in refs:
            source=source_map.get(e['path'])
            if not source or not has_original_quote(source,e['quote']):
                raise ValueError('客户理解引用须为同来源连续原文：'+section+' '+e['path'])
            if (source.get('relation')=='background_reference' and section!='profile.business') or (source.get('relation')=='customer_background' and not section.startswith('profile.')):
                raise ValueError('其他项目背景不能证明当前需求或角色：'+section)
        if section.startswith(('evolution.','lifecycle.')) and claim['date']:
            try:
                day=date.fromisoformat(claim['date'])
                if day.isoformat()!=claim['date'] or day>date.today():raise ValueError()
                if not any(claim['date'] in supported_dates(source_map[e['path']]) for e in refs):raise ValueError()
            except ValueError:raise ValueError('需求变化日期缺少对应来源支持：'+claim['date'])
    for group in ('evolution','lifecycle'):
        dates=[i['date'] for i in value[group] if i['date']]
        if dates!=sorted(dates):raise ValueError('需求变化与项目历程须按业务日期排序')
    return value

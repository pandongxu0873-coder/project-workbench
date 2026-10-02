export const relationships = { unknown: '未知／正常了解中', budget: '预算暂停', blocked: '内部受阻', concern: '方案或服务疑虑', no_need: '暂无需求', no_contact: '明确暂勿联系' };
export const scenarios = {
  first: { label: '首次拜访', goal: '确认业务问题与对接路径', questions: '目前最想解决什么问题？谁参与判断？何时适合进一步沟通？', materials: '本项目已知背景、待核实问题清单；案例适配性待确认', roles: '销售本人；需要方案讨论时邀请售前', acceptance: '记录客户原话、需求是否存在及允许的下一步', branches: '需求明确→约定方案澄清；尚不明确→补证据；暂勿联系→内部准备', draft: '想就【业务问题】向您了解实际情况，便于判断是否适合进一步交流。您方便时我们再约时间。' },
  return: { label: '再次拜访／沟通后更新', goal: '核对上次结论，记录变化并推进一个明确节点', questions: '上次待确认事项有什么新反馈？变化来自什么事实？下一步由谁确认？', materials: '上次沟通原文、未决事项、最新实际反馈', roles: '销售本人；按未决问题邀请售前／技术 TO／交付', acceptance: '事实与自己的判断分开；下一责任人和节点明确或标为待确认', branches: '已有答复→更新判断；已发出未回复→等待约定节点，不重复催促；条件变化→重选动作', draft: '关于【上次具体事项】，想与您核对【待确认点】。如目前还在内部讨论，我们按【双方约定节点】再对齐即可。' },
  relationship: { label: '客情维护／暂停', goal: '尊重客户节奏，区分关系与商机条件', questions: '暂停原因是否有明确原话？是预算、内部路径、服务疑虑还是没有需求？是否约定暂勿联系？', materials: '客户明确表达、服务反馈及双方约定；未回复本身不能推断关系差', roles: '销售本人；服务疑虑邀请交付负责人内部复盘', acceptance: '记录有依据的原因和联系边界；不将暂停等同于丢单', branches: '预算暂停→记录预算复议点；内部受阻→内部梳理路径；服务疑虑→先准备解决方案；暂无需求→等待新事实', draft: '想确认【具体事项】目前是否仍需要我们配合；如暂时不需要，我们尊重您的节奏，按约定再沟通。' },
  collaboration: { label: '内部协作／等待反馈', goal: '把明确问题交给合适角色，并记录真实回执', questions: '需要谁解决哪个问题？对方已接受还是仅已发送？约定何时反馈？', materials: '明确关联原文、事实、自己的判断、待解决问题与期望交付物', roles: '售前：方案；技术 TO：可行性与人天；交付：资源验收；销售助理：资料流程', acceptance: '记录具体责任人、期望结果、真实反馈；已发送不等于已接受或已完成', branches: '已发送→等待反馈；收到答复→核对能否验收；缺资料→补充明确来源', draft: '请协助【待解决问题】，参考本项目明确关联材料。期望产出【交付物】，请确认是否能承接及可反馈时间；尚未确认的范围请列出。' },
  procurement: { label: '采购路径', goal: '核实采购主体、流程与保护归属', questions: '谁发起、谁评审、谁采购、谁签约？流程及时间是否有来源？现有客户保护归属是否核实？', materials: '公开或客户提供的采购依据、资质清单、待核实主体', roles: '销售本人、销售助理；商务／法务按实际事项参与', acceptance: '明确已核实环节与未知环节，不把意向或入围当作签约', branches: '路径明确→准备对应材料；归属未知→先内部确认；采购暂缓→等待约定节点', draft: '为准备【项目】相关材料，想请您确认【采购流程或主体待核实项】及需要我们提供的清单。' },
  change: { label: '需求变更', goal: '分清原范围与新增范围，再进入现有报价流程', questions: '新增内容与原确认范围差在哪里？客户确认依据是哪一版？预算、人天和实际成本分别是什么？', materials: '原确认版本、新需求原文、边界与依赖；估算待技术复核', roles: '售前、技术 TO、交付；销售本人负责客户边界确认', acceptance: '变更边界与最新来源明确；未审核估算不作客户承诺', branches: '边界明确→现有报价与审批；范围不清→先澄清；审批未完成→保留草稿', draft: '关于【新增需求】，我们希望先核对其与【原确认范围／版本】的差异。工作量、费用与排期需评估后再确认。' },
  close: { label: '签约收口', goal: '核对合同范围、金额、主体与尚未完成的条件', questions: '签约主体及最终版本是否确认？审批、盖章、采购条件还缺什么？合同业绩的认定依据是什么？', materials: '客户确认版本、报价、审批依据、合同文本；内外口径分开', roles: '销售本人、销售助理、商务／法务；交付核对承诺', acceptance: '明确签约依据与未决条件；候选金额不进入已实现合同业绩', branches: '条件齐备→按实际流程完成签署；版本未确认→继续核验；已签→到合同业绩核对来源', draft: '想与您核对【合同版本】的【未决事项】。待双方完成必要确认后，再按约定流程推进签署。' },
};
export const emptyRound = () => ({ scenario: 'return', relationship: 'unknown', status: '准备中', contact: '', facts: '', judgement: '', action: '', owner: '', due: '', feedback: '', next_step: '', recontact_basis: '', topic: '' });
export const pauseGuidance = {
  budget: { goal: '先准备分期范围与业务价值依据，等待预算复议节点', materials: '预算暂停的原话、预算周期、可分期范围和价值测算；金额待核实', questions: '预算暂停是否已明确？下次复议需要什么依据？范围是否允许分期？', branches: '预算窗口未知→内部准备；窗口有约定→到约定节点核对；不得把暂无预算推断为关系差', draft: '如果目前需要等待预算安排，我们可以先整理【分期范围或业务价值依据】供您需要时参考，再按【双方约定预算复议节点】沟通。' },
  blocked: { goal: '帮助内部对接人准备讨论材料，先理清受阻环节', materials: '客户明确指出的内部阻点、评审角色与待补材料；不推定谁有决策权', questions: '具体卡在哪个内部环节？对接人需要什么支持？哪些角色尚待核实？', branches: '阻点明确→准备内部说明材料；责任未知→核实路径；未获同意不越级联系', draft: '如【具体内部讨论环节】需要支持，我们可先整理【价值说明或问题答复】给您参考，后续按您方便的节奏对齐。' },
  concern: { goal: '先复核方案或服务问题并准备解决方案，再谈推进', materials: '问题原话、影响范围、服务记录、内部整改方案和可验证结果', questions: '客户具体担忧什么？问题是否已解决并验证？谁负责整改反馈？', branches: '问题未解决→先内部复盘；有修复结果→按客户约定核验；不直接催报价或签约', draft: '关于【具体方案或服务问题】，我们希望先核对实际影响，并准备【处理方案及验证方式】。如您愿意，我们再按约定核验结果。' },
  no_need: { goal: '给客户空间，保留内部观察，等待出现新需求事实', materials: '暂无需求的明确表达、允许联系的边界与未来触发条件', questions: '暂无需求是否是客户原话？是否约定未来触发条件？是否允许后续联系？', branches: '没有新需求→内部观察不催促；有新事实→先核实；客户要求暂勿联系→选择对应状态', draft: '如果目前暂无相关需求，我们尊重您的安排；未来如有【业务变化】需要协助，您方便时再联系即可。' },
};
export function guidance(record, savedRecord) {
  const blocked = record.relationship === 'no_contact' || (savedRecord?.relationship === 'no_contact' && record.relationship !== 'no_contact');
  if (blocked) return { ...scenarios[record.scenario], goal: '尊重暂勿联系约定，仅做内部准备', draft: '', branches: '内部整理依据与待解决问题；有新事实时先记录恢复联系依据并保存状态，再准备联系', blocked: true };
  if (record.status === '已发出等待反馈') return { ...scenarios[record.scenario], draft: '', goal: '等待实际反馈，按已约定节点复盘', branches: '未回复不等于关系差；记录已发给谁、何时复盘，收到实际反馈后再推进', waiting: true };
  const base = scenarios[record.scenario];
  const pause = pauseGuidance[record.relationship];
  return pause ? { ...base, ...pause, draft: record.scenario === 'collaboration' ? base.draft : pause.draft } : base;
}
export function roundDraft(project, record, savedRecord) {
  const guide = guidance(record, savedRecord);
  if (!guide.draft) return '';
  if (record.scenario === 'collaboration') return `【内部协作草稿，未发送】\n项目：${project.title}\n依据：${project.sources.map(s => s.path).join('；')}\n沟通事实：${record.facts || '【待补充原话或事实】'}\n当前判断（个人判断）：${record.judgement || '【待判断】'}\n待办问题：${record.action || '【本轮要解决的问题】'}\n协作人：${record.owner || '【待确认】'}\n期望结果／下一步：${record.next_step || '【待确认交付物】'}\n${guide.draft}`;
  return `【沟通草稿，未发送；占位符需核实】\n${record.contact || '【联系人】'}，您好。${record.topic ? `想就“${record.topic}”与您沟通。` : '关于【本次对外沟通主题】，'}${guide.draft}\n项目：${project.title}`;
}

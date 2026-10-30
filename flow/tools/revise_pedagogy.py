"""Versioned questions: B1 tests added reasons; B2 tests limitations and interpretation."""
import json,copy,hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
# Each row is an authored interpretation of the corresponding added paragraph.
ROWS='''quiet-room|Arriving early and checking recording rules make the shared booking easier to use.|A quiet room does not by itself ensure that participants are comfortable being recorded.|Reserving the room also settles how all recordings may be used.
deadline|The explanation must connect the pictures to one event before the design is finished.|Meeting a deadline and producing an attractive layout do not ensure the task is properly answered.|A polished layout is the main evidence that the project meets its requirements.
club-budget|A shared cost record allows members to check spending and respond to higher printing prices.|Borrowed items can still involve transport, cleaning and responsibility.|Borrowing removes the need to include equipment in the practical plan.
group-roles|The shared question helps the group check whether separate parts form a coherent talk.|A fair division may need to change because equal numbers of tasks can require different effort.|Keeping the same roles is the best way to ensure equal effort.
lab-safety|Written steps and matching bottle names help the pair follow the demonstrated procedure.|Requesting clarification is part of careful work rather than evidence of poor preparation.|Students who start first have shown that their preparation is better.
feedback-rewrite|Comparing the endings helps Alex check whether the connection has become clearer.|Confident wording improves an argument only if its claim remains supported.|Making a conclusion sound more confident makes its evidence stronger.
late-train|Nearby lunch and a saved confirmation help the friends manage the revised visit.|Fixing the museum booking leaves a separate risk in the tighter return journey.|The revised museum slot is enough to make the rest of the afternoon secure.
hotel-request|The ticket identifies the stored bag, while the closing time affects when Ravi can collect it.|Identifying a practical need lets the hotel help without changing every check-in rule.|Agreement to store the bag implies agreement to early room access.
food-allergy|Checking sauces and repeating the request address gaps in the menu description.|Specific requests and checks of actual preparation are more reliable than dish names.|A different dish name provides sufficient evidence that the ingredient problem is resolved.
lost-wallet|Similar reports mean the officer needs more information before confirming a match.|Helpful reports distinguish confirmed details from uncertain memories.|Adding likely details is useful if it makes a possible match easier to recognise.
walking-route|Repeating the turns checks understanding, and the extra time affects the visitor's choice.|A useful route comparison considers the traveller's needs as well as distance.|The shortest route remains preferable once both routes have been explained.
ticket-refund|Knowing the refund method and processing time helps Ella plan her next purchase.|A right to a refund does not mean the money is immediately available.|Acceptance of the request means Ella can already use the returned funds.
parcel-neighbour|A shared arrangement keeps parcels out of a doorway where they could be mistaken.|A convenient favour needs agreed limits when circumstances change.|Success with the first deliveries establishes permission for future deliveries.
shopping-list|Expected use and storage time help Kai decide whether a larger pack is useful.|Value depends on what is used, not just a lower unit price.|The lowest unit price is the best measure of value for one person's shopping.
repair-appointment|The screen message and model number give the repair worker observable information.|An observed symptom is useful evidence without proving a particular internal cause.|A precise description of the message establishes which internal part has failed.
shared-kitchen|Including visitors in the agreement addresses a cause the first rule missed.|Shared rules should describe actions and remain open to revision after experience.|One untidy evening is enough to identify who is responsible for the ongoing problem.
library-return|Notes and alternative resources let Sam continue while another reader has the book.|Sam's deadline matters without automatically outweighing another reader's access.|Having a deadline gives Sam stronger grounds to keep the reserved copy.
weekend-plan|An early message lets both friends agree on a workable response to the delay.|Extra time helps manage uncertainty when changes are also communicated.|Leaving spare time makes it unnecessary to tell a friend about changes.
meeting-agenda|Separating updates leaves time for the decision and records who will check a conflict.|An agenda helps only when information, decisions and unresolved actions are clear.|Covering an agenda topic is sufficient evidence that the issue has been settled.
handover|Checking the actual order prevents the next worker from repeating an unverified promise.|A useful handover preserves checkable next-action information without unnecessary details.|The written promise is enough to establish that the replacement order exists.
clarify-request|A comparison is meaningful only after Dana checks that the figures use the same definition.|Clarifying a request's purpose does not remove the need to check comparability.|Numbers with similar headings provide a sound comparison once the reader is identified.
customer-delay|A recorded enquiry and a confirmed update time let another worker continue helping.|A useful response separates verified progress from estimates instead of inventing certainty.|A specific delivery promise is more helpful than explaining an uncertain estimate.
pilot-tool|A second type of task tests whether benefits extend beyond the first small project.|A faster update alone does not establish the tool's value across the whole workflow.|The measured speed improvement is enough to justify expansion to other departments.
email-tone|Giving the reason and checking the version clarify what needs to be sent.|Clear deadlines can coexist with politeness and openness to missing information.|Politeness is best achieved by making the required deadline less explicit.
museum-label|Plain language serves immediate needs while the guide offers additional detail.|Conciseness requires selecting essential context rather than simply removing information.|A shorter label is clearer whenever historical explanation is moved to the guide.
invitation-reply|Confirming details avoids assuming that earlier visits establish the current arrangement.|Practical questions respect this invitation without turning customs into universal rules.|A previous visit gives a reliable rule for later invitations from the same friend.
oral-history|Checking dates may explain apparent disagreement, and original wording preserves the accounts.|Disagreement can reveal perspective and uncertainty that a single merged story would hide.|A coherent report should combine memories into one account before presenting the evidence.
subtitle-choice|Comparing versions helps preserve the joke within the subtitle's space limit.|Natural wording may lose associations, so the translation involves a trade-off.|The version that sounds most natural reproduces the original meaning most fully.
festival-volunteer|Simple wording and observation help test whether visitors understand the sign.|Actual hesitation can reveal design problems that a larger sign alone will not solve.|Increasing the sign's size is the most direct evidence that the navigation problem is solved.
interview-consent|Keeping context and respecting the intended use guide how Rosa edits the interview.|Specific consent must be respected in the finished recording as well as written notes.|Removing a name from written notes is sufficient to satisfy the specific request.
plant-log|Initial measurements allow Dev to compare growth rather than only final height.|The pattern is consistent with an effect but a small setup cannot exclude other explanations.|Different growth provides enough evidence to identify light as the cause.
weather-backup|A final update time helps the group act despite the uncertainty in the forecast.|A forecast informs a decision while a backup provides an action if conditions change.|The better morning forecast makes the alternative plan unlikely to be needed and safe to omit.
average-journey|Response counts help the class judge whether each neighbourhood is adequately represented.|An average summarises a group without reliably predicting each individual's journey.|The class average is the most appropriate forecast for any student in the class.
energy-label|Expected hours of use determine whether a more efficient lamp brings worthwhile savings.|An energy rate and total future consumption differ because use depends on changing habits.|A lower measured energy rate establishes how much the household will save.
survey-question|Extra response options and separate topics make answers easier to interpret.|Neutral wording helps, but recording the actual question is needed when comparing results.|Neutral wording makes changes in future results comparable without checking the question.
source-check|Checking the tested materials limits what can be inferred about mixed household waste.|A promising laboratory result does not yet establish readiness for widespread use.|Success with the selected materials provides sufficient grounds for broad practical use.'''
rows={x.split('|')[0]:x.split('|')[1:] for x in ROWS.splitlines()}
original=json.loads((ROOT/'corpus_data/graded-packs.json').read_text());by={(p['family'],p['level']):p for p in original};out=[]
for old in original:
 p=copy.deepcopy(old);p['id']=old['id']+'-r30';p['revision_of']=old['id'];p['title']=old['title']+' · 修订题组';slug=p['family'].removeprefix('graded-');b1,b2,wrong=rows[slug];a2=by[(p['family'],'A2')]['body'];middle=by[(p['family'],'B1')]['body'][len(a2):].strip();last=by[(p['family'],'B2')]['body'][len(by[(p['family'],'B1')]['body']):].strip()
 def question(prompt,correct,alternatives,evidence,objective):
  opts=[correct]+alternatives;shift=int(hashlib.sha256((p['id']+prompt).encode()).hexdigest()[:4],16)%4;opts=opts[shift:]+opts[:shift]
  return {'prompt':prompt,'options':opts,'answer':opts.index(correct),'evidence':evidence,'objective':objective}
 facts=re.split(r'(?<=[.!?])\s+',a2)
 if p['level']=='B1':
  p['questions'][1]=question('What additional consideration guides the decision in the later part of the passage?',b1,[facts[0],facts[1],facts[2]],middle,'reason-and-condition')
 elif p['level']=='B2':
  p['questions'][0]=question('Which interpretation best captures the final paragraph?',b2,[wrong,b1,facts[0]],last,'interpretation-and-limits')
  p['questions'][1]=question('Which conclusion goes beyond what the passage supports?',wrong,[b2,b1,facts[1]],last,'unsupported-inference')
 else:p['questions'][1]['prompt']='Which detail of the sequence is directly supported by the text?';p['questions'][1]['objective']='factual-sequence'
 p['assessment_policy']='r30-level-targeted';out.append(p)
(ROOT/'corpus_data/revised-packs.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(len(out),'versioned packs; original answers untouched')

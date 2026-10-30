"""36 authored situations, each expanded into three labelled instructional versions."""
import json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from content_v07 import rotated_question
S=[]
def add(theme,slug,title,body,extension,discussion,term,meaning,question,correct,wrong,reason):
 S.append(dict(theme=theme,slug=slug,title=title,body=body,extension=extension,discussion=discussion,term=term,meaning=meaning,question=question,correct=correct,wrong=wrong,reason=reason))
add('campus','quiet-room','预约一个安静空间',
'Maya needs a quiet room for a group interview. She checks the library website before class. A small room is free on Thursday afternoon. She books it for one hour and sends the time to her partners. They bring a recorder and a list of questions.',
'Because the room is shared by several classes, Maya asks everyone to arrive five minutes early. She also checks whether the library allows recording inside the room.',
'The booking solves the problem of noise, although it does not guarantee that every speaker will feel comfortable. Maya therefore explains how the recording will be used and offers participants the choice of answering without being recorded.',
'quiet','安静的','When is the room free?','On Thursday afternoon',['On Monday morning','On Friday evening','On Sunday afternoon'],'They bring a recorder and a list of questions.')
add('campus','deadline','截止时间前确认要求',
'Leo has a history project due on Friday. He reads the task sheet after lunch. The project needs two pictures and a short explanation. He has the pictures but not the explanation. He writes a first version on Wednesday and asks his teacher one question.',
'When the teacher replies, Leo discovers that the explanation should connect the pictures to the same event. He changes his outline before spending more time on the final design.',
'A clear deadline can help organise work, but meeting it is different from meeting the task requirements. Leo keeps the task sheet beside his draft so that a polished layout does not hide missing evidence or an unclear explanation.',
'project','项目；课题','When is the project due?','On Friday',['On Tuesday','On Saturday','On Monday'],'The project needs two pictures and a short explanation.')
add('campus','club-budget','给社团活动做预算',
'An art club wants to hold a small exhibition. There are sixty pounds in its budget. The students need paper, labels, and tape. They borrow display boards from another club instead of buying new ones. This leaves enough money to print a simple invitation.',
'The treasurer records each cost in a shared table so that every member can check it. If the printing price rises, the group will reduce the number of invitations.',
'Borrowing equipment reduces the immediate cost, although it creates a responsibility to return it in good condition. The group includes transport and cleaning in its plan rather than assuming that an item described as free has no practical cost.',
'budget','预算','How much money does the club have?','Sixty pounds',['Six pounds','Sixteen pounds','Six hundred pounds'],'They borrow display boards from another club instead of buying new ones.')
add('campus','group-roles','让小组分工更清楚',
'Four students prepare a talk about local birds. Nina finds pictures and Omar checks the names. Jess writes the opening and Ben records the practice. Each person shares a short update on Tuesday. They meet again on Thursday to put the parts together.',
'Although the tasks are separate, the students agree on one main question for the talk. They use the Thursday meeting to check whether each part helps answer that question.',
'Equal task counts do not necessarily mean equal effort, since finding reliable names may take longer than locating pictures. The group asks members to report difficulties early and allows roles to change when the original division no longer fits the work.',
'update','进展说明','When does each person share an update?','On Tuesday',['On Monday','On Friday','On Sunday'],'They meet again on Thursday to put the parts together.')
add('campus','lab-safety','实验前先读标签',
'Sara joins a school science activity. A teacher gives each pair a tray and a paper guide. Sara reads the labels before opening any bottle. One label is difficult to read, so she asks the teacher for help. Her partner waits until the instructions are clear.',
'The pair writes down the steps that the teacher demonstrates. Before they begin, they check that the names on the bottles match the names in their guide.',
'Waiting for clarification may feel slow when other pairs have started, but guessing would introduce an unnecessary risk. The teacher treats a request for help as part of careful work, rather than as evidence that a student has failed to prepare.',
'label','标签','Who helps Sara with the unclear label?','The teacher',['A bus driver','A librarian','A shop owner'],'One label is difficult to read, so she asks the teacher for help.')
add('campus','feedback-rewrite','把评语变成可修改的句子',
'Alex receives a comment on an English paragraph. The teacher says the final sentence is unclear. Alex underlines the sentence and reads the earlier example again. He adds a reason that connects the example to his main idea. He keeps both versions in his notebook.',
'Instead of changing every sentence at once, Alex asks a partner to compare the two endings. The partner explains which version makes the connection easier to follow.',
'A smoother sentence is useful only if it still expresses the intended claim. Alex checks whether his new reason is supported by the example, recognising that confident wording can make an unsupported conclusion sound more convincing without making it more accurate.',
'paragraph','段落','Which part does the teacher call unclear?','The final sentence',['The title','The first word','The page number'],'He keeps both versions in his notebook.')
add('travel','late-train','列车延误后重新安排',
'A train to the coast is thirty minutes late. Mei checks the station screen and sends a message to her friend. Their museum visit starts at two. Mei asks the museum whether a later arrival is possible. A member of staff moves their visit to three.',
'Because the revised visit leaves less time for lunch, the friends choose a cafe near the museum. Mei saves the confirmation message in case a different staff member checks their booking.',
'The later slot solves one problem but makes the return journey tighter. Rather than treating the new booking as a complete solution, the friends check the final train and agree which part of the afternoon they will shorten if another delay occurs.',
'arrival','到达','What is the new museum visit time?','Three',['One','Two','Four'],'A member of staff moves their visit to three.')
add('travel','hotel-request','向酒店说明实际需求',
'Ravi arrives at a hotel before check-in time. His room is not ready yet. He asks whether he can leave his bag at the desk. The receptionist gives him a numbered ticket for the bag. Ravi keeps the ticket and goes for a short walk.',
'When he returns, Ravi shows the ticket rather than describing the bag from memory. He also asks what time the reception desk closes in the evening.',
'A polite request is easier to answer when it identifies the practical need instead of assuming an exception to every rule. Ravi separates storing a bag from entering the room early, allowing the receptionist to offer help within the services currently available.',
'receptionist','接待员','What does Ravi receive for his bag?','A numbered ticket',['A room key','A museum map','A train timetable'],'The receptionist gives him a numbered ticket for the bag.')
add('travel','food-allergy','点餐时把要求说清楚',
'Lina orders soup at a restaurant. She tells the server that she cannot eat peanuts. The server checks the ingredients with the kitchen. The soup contains peanut sauce, so Lina chooses another dish. She asks the server to check the second dish as well.',
'Although the menu lists several ingredients, Lina does not assume that the list describes every sauce. The server repeats her request to confirm what the kitchen needs to check.',
'A dish with a different name is not automatically suitable, and a confident guess from either person would not resolve the uncertainty. The exchange works because the request is specific and the server checks the actual preparation rather than relying only on the menu title.',
'ingredients','配料','Why does Lina choose another dish?','The soup contains peanut sauce',['The restaurant is closed','The soup is too expensive','The server loses the order'],'The server checks the ingredients with the kitchen.')
add('travel','lost-wallet','描述遗失物品',
'Tom cannot find his wallet after a bus trip. He calls the transport office that afternoon. He describes a small brown wallet with a blue card inside. The officer asks for the bus number and travel time. Tom checks his ticket before giving the details.',
'Because several similar wallets have been reported, the officer does not confirm a match immediately. Tom leaves a contact number and asks when he should check again.',
'Specific details make the report more useful, but they should not be invented to make a possible match seem certain. Tom distinguishes what he remembers from what his ticket confirms, helping the officer compare the report with items actually recovered.',
'wallet','钱包','What colour is the wallet?','Brown',['Green','Red','White'],'The officer asks for the bus number and travel time.')
add('travel','walking-route','比较两条步行路线',
'A visitor asks Noor how to reach the riverside market. The shortest path has many steps. Another path goes past the library and has no steps. The visitor has a heavy bag, so Noor explains the second route. She points out the library on a street map.',
'The visitor repeats the main turns to check that he has understood them. Noor mentions that the second route takes about ten minutes longer than the first.',
'The best route depends on the traveller as well as the distance. Noor explains the extra time instead of hiding it, so the visitor can weigh a longer walk against the difficulty of carrying a heavy bag up several flights of steps.',
'route','路线','Which route has no steps?','The route past the library',['The shortest path','The path over the hill','The path behind the station'],'The visitor has a heavy bag, so Noor explains the second route.')
add('travel','ticket-refund','确认退票条件',
'Ella buys a ticket for a boat tour. Heavy rain changes her plans for the day. She reads the ticket conditions before calling the office. A refund is possible until six that evening. Ella sends her booking number and keeps the reply from the office.',
'The reply explains that the refund will return to the original payment method. Ella checks the expected processing time instead of buying a replacement ticket immediately.',
'A refundable ticket and an immediate refund are different promises. By checking both the cancellation deadline and the processing period, Ella can make a new plan without assuming that money will be available again as soon as the request is accepted.',
'refund','退款','Until what time is a refund possible?','Six that evening',['Eight that morning','Noon the next day','Midnight the next week'],'Ella sends her booking number and keeps the reply from the office.')
add('life','parcel-neighbour','代收包裹时确认身份',
'A courier brings a parcel for Jo while she is out. Her neighbour accepts it and sends her a message. The message includes the flat number but not a photo of the address label. Jo collects the parcel that evening. She checks the name before taking it home.',
'When another parcel arrives later, the neighbour follows the same simple arrangement. They agree not to leave either parcel in the shared doorway, where someone could pick it up by mistake.',
'The arrangement is convenient because both neighbours know what has been agreed. It would be less reliable if either person assumed that every delivery could be accepted indefinitely, so they discuss what to do when one of them is away for several days.',
'parcel','包裹','When does Jo collect the parcel?','That evening',['The following month','Before the courier arrives','On the next holiday'],'She checks the name before taking it home.')
add('life','shopping-list','购物前先检查已有物品',
'Kai plans three simple meals for the week. He checks the kitchen before writing a shopping list. There is rice and pasta but no fresh fruit. He adds fruit and vegetables to the list. At the shop, he compares the amount he needs with the pack size.',
'Because a larger pack is not always useful for one person, Kai checks how long the food will keep. He chooses a smaller amount when he has no plan to use the rest.',
'A lower price per unit can still lead to a higher total cost if much of the purchase is unused. Kai compares the price with likely use rather than assuming that the largest pack offers the best value in every situation.',
'amount','数量；量','What is missing from the kitchen?','Fresh fruit',['Rice','Pasta','A shopping list'],'At the shop, he compares the amount he needs with the pack size.')
add('life','repair-appointment','预约维修时描述问题',
'A washing machine stops during a cycle. Ana writes down the message on its screen. She calls the repair office and describes what happened. The office offers a visit on Wednesday morning. Ana asks about the visit fee before confirming the appointment.',
'The person on the phone asks whether the machine has shown the same message before. Ana gives the model number but does not guess which internal part has failed.',
'A useful description separates observed behaviour from a proposed explanation. Recording the screen message will not identify every possible cause, but it gives the repair worker more reliable starting information than an unsupported claim that a particular part must be broken.',
'appointment','预约','When is the repair visit offered?','Wednesday morning',['Tuesday evening','Friday afternoon','Sunday night'],'Ana asks about the visit fee before confirming the appointment.')
add('life','shared-kitchen','共享厨房的使用约定',
'Three friends share a kitchen in a small flat. Clean cups are often difficult to find in the morning. They agree to wash their own cups after each meal. A small tray beside the sink holds cups that are still wet. They discuss the arrangement again after one week. They write the agreement on a card.',
'Although the first agreement sounds simple, the friends notice that guests also use the cups. They add a short rule about cleaning after visitors leave rather than blaming one person for every missing cup.',
'A shared rule works better when it describes a visible action and can be revised after experience. The friends avoid treating a single untidy evening as proof of permanent habits, while still making clear what each person is expected to do.',
'agreement','约定；协议','Where do they put wet cups?','On a tray beside the sink',['Under a bed','In a suitcase','On the balcony floor'],'They agree to wash their own cups after each meal.')
add('life','library-return','归还图书前处理提醒',
'An email reminds Sam to return a library book. The book is due on Tuesday. Sam still needs two chapters for a class task. He checks whether he can renew the book online. Another reader has reserved it, so he returns it on time.',
'Before returning the book, Sam notes the pages he needs and asks about another copy. The librarian explains which resources he can use while waiting for the book to become available again.',
'Renewal would be convenient for Sam, but the reservation shows that someone else also needs access. Asking for alternatives allows him to continue his work without assuming that his own deadline should automatically take priority over every other reader.',
'renew','续借；更新','When is the book due?','Tuesday',['Thursday','Saturday','Sunday'],'Another reader has reserved it, so he returns it on time.')
add('life','weekend-plan','把周末计划排得可执行',
'Mina wants to study and see a friend on Saturday. She lists the tasks that must be finished first. A short report needs one more paragraph. She writes it in the morning and meets her friend after lunch. She leaves the evening free for anything unfinished.',
'When the report takes longer than expected, Mina sends a message before their meeting time. Her friend suggests a later start, and they agree on a new time that works for both.',
'Leaving space in a plan is different from assuming that every task will go smoothly. Mina uses the extra time to respond to a real delay, while communicating the change early enough for her friend to adjust rather than simply waiting without information.',
'unfinished','未完成的','When does Mina plan to meet her friend?','After lunch',['Before breakfast','At midnight','On Friday'],'She leaves the evening free for anything unfinished.')
add('work','meeting-agenda','开会前说清要做的决定',
'A small team meets every Monday morning. This week, Priya sends an agenda before the meeting. The first item is choosing a date for a customer interview. Each person brings two possible dates. The team writes the final date in a shared calendar.',
'Because the meeting has a clear decision to make, Priya keeps general updates in a separate message. If a date cannot be agreed, the team records who will check the remaining conflict.',
'An agenda does not make a discussion useful by itself. Its value depends on whether participants understand the decision, have the information needed to make it, and leave with a record of what remains unresolved rather than a vague feeling that the topic has been covered.',
'agenda','议程','What is the first meeting item?','Choosing an interview date',['Buying office chairs','Changing the company name','Planning a holiday party'],'Each person brings two possible dates.')
add('work','handover','交接时留下可追踪的信息',
'Chen finishes a shift at a small shop. One customer is waiting for a replacement item. Chen writes the order number and the promised delivery date in the handover note. He tells the next worker where to find the note. He does not include the customer\'s personal story.',
'The next worker checks that the replacement has actually been ordered before repeating the promise. If the delivery date changes, she will update the note and contact the customer through the normal system.',
'A handover should preserve the information required for the next action without spreading unnecessary details. Repeating an earlier promise is not the same as verifying it, so the written record points to something that another worker can check.',
'replacement','替换物；补发物品','What does Chen record with the order number?','The promised delivery date',['The customer\'s favourite film','The weather forecast','A colleague\'s holiday dates'],'He tells the next worker where to find the note.')
add('work','clarify-request','澄清一个模糊的工作请求',
'A manager asks Dana for a quick report. Dana asks who will read it and when it is needed. The manager needs a one-page summary by Thursday. Dana includes the main result and two open questions. She sends a short outline before writing the final version.',
'When the manager reviews the outline, he asks for a comparison with last month. Dana checks whether the available figures use the same definition before adding that comparison.',
'A request can sound clear while leaving its purpose unspecified. Asking about the reader and deadline helps Dana select relevant details, but the comparison still requires care because two numbers are not necessarily comparable simply because they appear under similar headings.',
'summary','摘要；概述','How long should the summary be?','One page',['Ten pages','One hundred pages','A full book'],'She sends a short outline before writing the final version.')
add('work','customer-delay','延迟交付时给出下一步',
'A customer asks why a package has not arrived. The support worker checks the tracking record. The parcel is waiting at a local delivery centre. The worker explains what the record shows and opens an enquiry. She gives the customer a reference number for the enquiry.',
'Although the worker cannot promise a delivery time that has not been confirmed, she can explain when the next update is expected. She records the enquiry so another worker can follow it later.',
'An apology may acknowledge inconvenience without resolving the practical problem. The response becomes useful when it distinguishes verified information from an estimate and gives the customer a specific way to follow progress, rather than replacing uncertainty with an unsupported promise.',
'enquiry','查询；询问','Where is the parcel waiting?','At a local delivery centre',['At the customer\'s home','On a museum shelf','Inside the support office'],'She gives the customer a reference number for the enquiry.')
add('work','pilot-tool','先试用工具再决定推广',
'A design team runs a trial of a new planning tool for one week. Five people use it on a small project. They record time spent updating tasks and fixing mistakes. Updates become faster, but two people find the search function difficult. The team lists these problems before deciding what to do next.',
'Because the test covers only one small project, the team does not assume that every department will benefit in the same way. It plans a second trial with a different kind of task.',
'A faster update is a useful result, although it measures only one part of the workflow. Before expanding the tool, the team considers training time, search difficulties, and whether the trial included the kinds of mistakes that matter most in everyday work.',
'trial','试用；试验','How long is the first trial?','One week',['One hour','Six months','Two years'],'The team lists these problems before deciding what to do next.')
add('work','email-tone','邮件中区分请求与指责',
'Ali needs a file from another team. His first email says that the file is still missing. He changes the message to name the file and explain the deadline. He asks whether the team can send it by three. He also offers to discuss a different time if necessary.',
'The revised message explains why the file is needed without guessing why it has not arrived. When the other team replies, Ali confirms which version of the file will be sent.',
'Polite language does not require hiding a real deadline. The message works because it makes the required action clear while leaving room for information that Ali does not yet have, including a possible version problem or a conflict with another urgent task.',
'deadline','截止时间','By what time does Ali request the file?','Three',['Six','Midnight','Nine the next morning'],'He also offers to discuss a different time if necessary.')
add('culture','museum-label','给陌生读者写展品说明',
'A museum volunteer writes a label for an old cooking pot. Some visitors do not know the local festival connected with it. The volunteer adds one sentence about when the pot was used. She keeps the label short and asks a visitor to read it. The visitor points to a word he does not understand.',
'Instead of adding a long history to the label, the volunteer explains the unfamiliar word in plain language. A longer description remains available in a printed guide for visitors who want more detail.',
'Conciseness involves choosing what a reader needs, rather than removing context indiscriminately. The volunteer cannot explain every historical debate on a small label, but she can avoid assuming that a visitor already shares the background knowledge of the person who wrote it.',
'visitor','参观者','What does the visitor identify?','A word he does not understand',['A broken window','A missing ticket','An incorrect room number'],'She keeps the label short and asks a visitor to read it.')
add('culture','invitation-reply','回复邀请并确认细节',
'Grace receives an invitation to dinner at a friend\'s home. She thanks her friend and says she can come. The invitation gives a day but no time. Grace asks what time she should arrive. She also asks whether she can bring something for the meal.',
'When her friend replies, Grace confirms the time in a short message. She avoids assuming that a habit from an earlier visit applies to every home or occasion.',
'Asking a practical question can show consideration without turning a single custom into a universal rule. Grace treats her friend as the best source for this particular invitation, recognising that family preferences and the purpose of a gathering may matter as much as broad cultural expectations.',
'invitation','邀请','Which detail is missing from the invitation?','The arrival time',['The friend\'s name','The day','The fact that it is dinner'],'Grace asks what time she should arrive.')
add('culture','oral-history','保存口述故事中的不同视角',
'A student asks two relatives about an old neighbourhood market. One remembers the food and the other remembers the music. The student writes both accounts in a notebook. She marks who described each detail. She keeps each account separate. She asks a second question when the accounts use different street names.',
'Because the relatives may be remembering different years, the student checks the dates before deciding that one description is wrong. She keeps the original wording beside her own summary.',
'Differences between memories can be valuable evidence about perspective as well as possible mistakes. Combining the accounts into a single confident story would make the report simpler, but it could erase the uncertainty that a careful reader needs in order to understand the sources.',
'account','叙述；描述','What does the second relative remember?','The music',['The train fares','The school uniforms','The weather report'],'She marks who described each detail. She keeps each account separate.')
add('culture','subtitle-choice','字幕中保留哪些信息',
'A student makes English subtitles for a short school film. One speaker uses a local expression. A word-for-word translation is difficult to understand. The student writes a shorter explanation and checks it with the speaker. She tests whether a viewer can read it before the next line appears.',
'Although the subtitle must be brief, the student tries to keep the reason for the speaker\'s joke. She compares two versions and asks which one better fits the scene.',
'Every short subtitle involves choices about timing and meaning. A version that sounds natural may still lose an important association, so the student records the main trade-off instead of claiming that one English sentence reproduces everything carried by the original expression.',
'expression','表达；用语','Who checks the shorter explanation?','The speaker',['A bus driver','A hotel receptionist','A customer waiting outside'],'She tests whether a viewer can read it before the next line appears.')
add('culture','festival-volunteer','志愿服务中的清晰指引',
'A festival volunteer stands near the entrance to a community hall. Visitors ask where to collect a programme. The volunteer points to a table beside the main door. When the queue grows, he moves a sign so people can see it earlier. He checks that the sign does not block the entrance.',
'The sign uses a short sentence and a simple arrow because some visitors are reading English as an additional language. The volunteer watches whether people still need to ask the same question.',
'A sign that is clear to its designer may not be clear to someone arriving in a crowd. Watching where visitors hesitate provides more useful feedback than assuming that a larger sign alone will solve every problem with position, wording, and direction.',
'entrance','入口','Where can visitors collect a programme?','At a table beside the main door',['In the car park','On the roof','At a distant station'],'He checks that the sign does not block the entrance.')
add('culture','interview-consent','采访前确认如何使用回答',
'Rosa interviews a neighbour for a class project. Before starting, she explains that the class will hear a short recording. The neighbour agrees to speak but asks Rosa not to use his full name. Rosa writes that request beside her questions. The class is the audience for the recording. She checks the final clip with him before sharing it.',
'When Rosa edits the interview, she keeps enough context for the answer to make sense. She does not treat permission to record as permission to use every sentence in any future project.',
'The interview is easier to manage when the intended audience and use are discussed in advance. Respecting a specific request also requires checking the finished work, because a name might appear in a spoken introduction even if it has been removed from the written notes.',
'audience','听众；受众','What does the neighbour ask Rosa to omit?','His full name',['Every question','The project title','The recording date'],'She checks the final clip with him before sharing it.')
add('science','plant-log','记录植物生长的条件',
'Dev puts two plants beside a classroom window. He gives each plant the same amount of water. One plant receives more light than the other. Dev measures their height every Friday. He records the numbers before discussing what might explain the difference.',
'Because the plants were not exactly the same size at the start, Dev keeps their first measurements in the table. He compares changes in height rather than only the final numbers.',
'A difference in growth may be consistent with an effect of light, but this small comparison does not rule out every other explanation. Dev describes the observed pattern and the limits of the setup instead of presenting one classroom observation as a universal result.',
'height','高度','When does Dev measure the plants?','Every Friday',['Every Monday evening','Once a year','Only on the first day'],'He records the numbers before discussing what might explain the difference.')
add('science','weather-backup','用天气信息调整计划',
'A walking group checks a weather forecast on Friday. Rain is likely on Saturday afternoon. The group moves its walk to the morning. The leader asks everyone to bring a light raincoat. She says the plan will be checked again before the group leaves.',
'Although the forecast suggests a better chance of dry weather in the morning, the leader does not promise that it will stay dry. She sends the time of the final update to the group.',
'A forecast supports a decision without removing uncertainty. The group combines the latest information with a practical alternative, so a change in the forecast leads to a clear action rather than confusion about whether the earlier message was a guarantee.',
'forecast','预报','When does the group move its walk?','Saturday morning',['Friday night','Sunday evening','Monday afternoon'],'She says the plan will be checked again before the group leaves.')
add('science','average-journey','平均时间之外还有什么',
'A class asks students how long they travel to school. Most answers are between ten and twenty minutes. Two students travel for over an hour. The class writes the average and also draws a chart of all the answers. The chart shows a difference that one number can hide.',
'When the class compares two neighbourhoods, it checks how many students answered from each one. A group with only a few responses may not describe every student who lives there.',
'The average is not wrong merely because the journeys vary, but it answers a limited question. Showing the spread and the number of responses helps readers avoid treating a summary for the class as a reliable prediction for any particular student.',
'average','平均数；平均的','How long do two students travel?','Over an hour',['Under one minute','Exactly ten minutes','Three days'],'The class writes the average and also draws a chart of all the answers.')
add('science','energy-label','比较耗电量前先对齐条件',
'A family compares two lamps in a shop. The lamps provide similar light but use different amounts of electricity. One label gives energy use for a fixed number of hours. The family checks that both labels use the same number of hours. They compare the price as well as the energy figure.',
'Because the family uses the lamp for only part of each evening, it estimates the running time before judging the likely saving. The most expensive model is not selected automatically.',
'A smaller energy figure can be meaningful only when the compared conditions are understood. The family distinguishes a measured rate from total household use and recognises that an estimate of future savings depends on habits that may change.',
'compare','比较','What do the family check about the labels?','That they use the same number of hours',['That they have the same colour','That they show the same shop address','That they use the same brand name'],'They compare the price as well as the energy figure.')
add('science','survey-question','调查问题如何影响答案',
'Zoe writes a survey about the school canteen. Her first question asks why the food is always boring. A friend points out that the question already includes a judgement. Zoe changes it to ask what students think of the menu. She tests the new question with three classmates.',
'The classmates suggest adding an option for people who do not use the canteen. Zoe also checks whether asking about price and taste in the same question makes the answers difficult to interpret.',
'Neutral wording cannot remove every source of bias, but it can avoid pushing respondents toward a conclusion before they answer. Zoe records the revised question so that changes in future results are not confused with changes in what was actually asked.',
'survey','调查','How many classmates test the new question?','Three',['Thirty','One hundred','None'],'Her first question asks why the food is always boring.')
add('science','source-check','转发科学消息前查来源',
'Imran sees a message about a new way to recycle plastic. The message has no link to a study. He searches for the original report before sharing it. The report describes a small laboratory test. Imran adds that detail when he discusses the result with his class. He asks what the evidence can show.',
'Because the test uses carefully selected materials, Imran checks whether mixed household waste was included. He separates what the researchers tested from what a social media headline suggests.',
'A promising laboratory result can justify further research without showing that a method is ready for widespread use. Keeping the scale and conditions visible allows the class to recognise progress while avoiding a claim that goes beyond the evidence described in the report.',
'evidence','证据','What kind of test does the report describe?','A small laboratory test',['A worldwide household programme','A ten-year city survey','A completed national recycling system'],'He searches for the original report before sharing it.')


def build():
 packs=[]
 for s in S:
  for level in ('A2','B1','B2'):
   id='graded-'+s['slug']+'-'+level.lower();body=s['body']+(' '+s['extension'] if level in ('B1','B2') else '')+(' '+s['discussion'] if level=='B2' else '')
   parts=re.split(r'(?<=[.!?])\s+',body);q1e=max(re.split(r'(?<=[.!?])\s+',s['body']),key=lambda x:len(set(re.findall('[a-z]+',s['correct'].lower())) & set(re.findall('[a-z]+',x.lower()))))
   if s['slug']=='lab-safety':q1e=next(x for x in parts if 'asks the teacher' in x)
   if s['slug']=='weather-backup':q1e=next(x for x in parts if 'moves its walk' in x)
   # A2 fact retrieval; later versions also ask about the purpose of a stated action.
   qs=[rotated_question(id,0,s['question'],[s['correct'],*s['wrong']],0,q1e),rotated_question(id,1,'Which action is explicitly described in the passage?',[s['reason'],'Everyone cancels the activity without checking.','The main character refuses to ask any questions.','No record or further action is made.'],0,s['reason'])]
   bandtask={'A2':'用3–5句复述人物、事件和下一步行动；回答一个具体细节问题。','B1':'用自己的话解释选择及原因，追问一个未说明的细节，再换成自己的经历。','B2':'比较两种选择，区分已知事实与推测，说明一项限制，并回应一种不同看法。'}[level]
   packs.append({'id':id,'family':'graded-'+s['slug'],'title':s['title']+' · '+level,'level':level,'theme':s['theme'],'genre':'story' if level=='A2' else 'article','body':body,'questions':qs,'dictation_index':min(1,len(parts)-1),'speaking':bandtask,'writing':('用40–70词写一段相似场景，说明人物、问题和下一步。' if level=='A2' else '用80–120词描述一个相似问题，说明你的选择和原因。' if level=='B1' else '用130–190词比较可行方案，说明证据、限制与取舍。'),'vocabulary':[{'term':s['term'],'meaning':s['meaning'],'example':next((p for p in parts if re.search(r'(?<![a-z])'+re.escape(s['term'])+r'(?![a-z])',p,re.I)),s['body'])}], 'tags':['分级情境','细节理解' if level=='A2' else '解释原因' if level=='B1' else '比较与反思'],'grammar':['tense-present'],'knowledge':[{'node':'tense-present','quote':parts[0],'explanation':'用一般现在时叙述教学情境中的行动与状态；这是教学关联，阅读不等于已掌握该语法。'}],'source':'Flow 原创分级教学情境；编排分级，持续校对中','grading_basis':{'method':'authored-instructional','rationale':{'A2':'短句与具体日常情境，定位明确事实，短句输出。','B1':'在同一情境上增加因果、条件与行动解释，要求连贯复述。','B2':'增加限制、取舍和观点比较，要求有依据的较长表达。'}[level],'certified':False}})
 for p in packs:
  if p['level']=='A2':continue
  anchor=next((x for x in re.split(r'(?<=[.!?])\s+',p['body']) if re.match(r'^(Because|When|Although|If)\b',x)),None)
  if anchor:
   p['grammar'].append('clause-adverb');p['knowledge'].append({'node':'clause-adverb','quote':anchor,'explanation':'句首引导词连接条件、时间、原因或让步与后续行动；结合本句核对逻辑关系。'})
 return packs
if __name__=='__main__':
 packs=build();Path(sys.argv[1]).write_text(json.dumps(packs,ensure_ascii=False,indent=1),encoding='utf-8');print(len(S),'situations',len(packs),'versions')

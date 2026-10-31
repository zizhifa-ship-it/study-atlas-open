"""知识模块结构、第二轮自查与个人资料保护。模型全部使用替身。"""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from integrations import IntegrationError
from knowledge import build_knowledge, validate_knowledge, review_modules, audit_modules
from server import LibraryStore

SOURCE = "网络使用 IP 进行跨网寻址，DHCP 自动分配 IP 地址。TCP 会确认与重传，UDP 不提供可靠性保证。"

def module(mid='m1'):
    return {"id":mid,"title":"IP 与地址分配","objective":"解释 IP 与 DHCP 的关系","prerequisites":[],
            "notes":"## 核心概念\nIP 用于跨网寻址，DHCP 自动分配 IP 地址。[S1]",
            "concepts":[{"name":"IP","explanation":"逻辑地址"},{"name":"DHCP","explanation":"自动分配地址"}],
            "examples":["设备加入网络后自动获得地址。"],"pitfalls":["地址分配不等于端到端可靠性。"],
            "questions":[{"question":"DHCP 解决什么问题？","answer":"自动分配 IP 地址。"}],"evidence":["DHCP 自动分配 IP 地址"]}

class FakeKnowledgeAI:
    def __init__(self):
        self.lock=threading.Lock();self.calls=[];self.state={};self.before_review=lambda:None;self.module_count=2
        self.review={"summary":"已检查本次资料中的概念、例子和引用。","issues":[],"corrections":[]}
    def read(self,name):
        return {"model":{"model":"test-model"}} if name=='harness' else copy.deepcopy(self.state.get(name, {}))
    def write(self,name,data):
        self.state[name]=copy.deepcopy(data)
    def harness_generate(self,prompt):
        self.calls.append(prompt)
        if '独立的第二轮自查' in prompt:
            self.before_review();answer=self.review
        elif '请把课程规划' in prompt:
            answer={"title":"网络地址知识模块","overview":"先理解地址，再理解自动分配。","modules":[{"title":"IP 与 DHCP","objective":"解释寻址和分配","prerequisites":[]},{"title":"传输可靠性","objective":"比较 TCP 与 UDP","prerequisites":["IP"]}]}
            answer['modules']=(answer['modules']*3)[:self.module_count]
        else:
            data=json.loads(prompt.split('资料：\n')[-1]);answer=module(data['module']['id'])
        return {"content":json.dumps(answer,ensure_ascii=False),"model":"test-model"}

class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'library.json'
        data={"schemaVersion":1,"revision":0,"categories":[{"id":"net","name":"网络基础","parentId":None,"color":"green","description":""}],"videos":[{"id":"video","title":"测试课程","url":"https://example.com/lesson","categoryId":"net","author":"","durationSec":0,"tags":[],"status":"todo","favorite":False,"summary":"保留已有的学习总结。","transcript":SOURCE,"notes":[{"id":"n1","text":"个人批注不能覆盖。","timeSec":None,"createdAt":"2026-10-27"}],"createdAt":"2026-10-27","updatedAt":"2026-10-27"}],"insights":[]}
        self.path.write_text(json.dumps(data));self.store=LibraryStore(self.path);self.ai=FakeKnowledgeAI()
    def tearDown(self):self.temp.cleanup()
    def build(self):return build_knowledge(self.store,self.ai,'video',lambda message:None)
    def test_plan_details_independent_review_and_persistence(self):
        knowledge=self.build();v=self.store.read()['videos'][0]
        self.assertEqual(len(self.ai.calls),4)
        self.assertIn('独立的第二轮自查',self.ai.calls[-1])
        self.assertEqual(len(knowledge['modules']),2)
        self.assertEqual(v['knowledge']['review']['status'],'reviewed')
        self.assertEqual(v['summary'],'保留已有的学习总结。')
        self.assertEqual(v['notes'][0]['text'],'个人批注不能覆盖。')
        self.assertEqual(LibraryStore(self.path).read()['videos'][0]['knowledge'],knowledge)
    def test_unsupported_quote_is_visible_and_not_marked_verified(self):
        m=module();m['evidence']=['资料里根本没有的示例和概念']
        issues=audit_modules([m],SOURCE)
        self.assertTrue(issues)
        self.assertFalse(issues[0]['resolved'])
    def test_review_applies_actual_correction_and_keeps_audit_trail(self):
        draft={"modules":[module()]}
        review={"summary":"纠正过于简化的表述。","issues":[{"moduleId":"m1","severity":"warning","kind":"uncertainty","problem":"正文需说明可靠性边界。","suggestion":"区分寻址与可靠性。"}],"corrections":[{"issueIndex":0,"moduleId":"m1","field":"notes","value":"IP 负责寻址；TCP 提供确认与重传。[S1]","reason":"补充寻址与传输可靠性的边界。"}]}
        revised,report=review_modules(lambda prompt:{"content":json.dumps(review)},draft,SOURCE,'原始字幕')
        self.assertIn('TCP',revised[0]['notes'])
        self.assertTrue(report['issues'][0]['resolved'])
        self.assertEqual(len(report['corrections']),1)
        self.assertNotIn('TCP',draft['modules'][0]['notes'])
    def test_claimed_correction_without_change_stays_unresolved(self):
        draft={"modules":[module()]}
        review={"summary":"检查范围有限。","issues":[{"moduleId":"m1","severity":"warning","kind":"uncertainty","problem":"需要核对。","suggestion":"回看课程。"}],"corrections":[{"issueIndex":0,"moduleId":"m1","field":"notes","value":draft['modules'][0]['notes'],"reason":"声称修正。"}]}
        _,report=review_modules(lambda p:{"content":json.dumps(review)},draft,SOURCE,'原始字幕')
        self.assertEqual(report['status'],'needs_review')
        self.assertFalse(report['issues'][0]['resolved'])
    def test_invalid_review_does_not_replace_saved_knowledge(self):
        old=self.build();self.ai.review['issues']=[{"moduleId":"unknown","severity":"warning","kind":"evidence","problem":"无效模块","suggestion":"核对"}]
        with self.assertRaises(IntegrationError):self.build()
        self.assertEqual(self.store.read()['videos'][0]['knowledge'],old)
    def test_invalid_correction_preserves_module_and_stays_unresolved(self):
        draft={"modules":[module()]}
        review={"summary":"检查依据摘录。","issues":[{"moduleId":"m1","severity":"warning","kind":"evidence","problem":"摘录需要核对。","suggestion":"回到原资料。"}],"corrections":[{"issueIndex":0,"moduleId":"m1","field":"evidence","value":"错误地返回字符串","reason":"修订摘录。"}]}
        revised,report=review_modules(lambda p:{"content":json.dumps(review)},draft,SOURCE,'原始字幕')
        self.assertEqual(revised,draft['modules'])
        self.assertFalse(report['issues'][0]['resolved'])
        self.assertEqual(report['corrections'],[])
        self.assertIn('格式校验',report['issues'][0]['suggestion'])
    def test_source_edited_during_review_does_not_get_old_results(self):
        def edit():
            data=self.store.read();data['videos'][0]['transcript']+='用户新补充的资料。';self.store.save(data)
        self.ai.before_review=edit
        with self.assertRaises(IntegrationError):self.build()
        self.assertIsNone(self.store.read()['videos'][0]['knowledge'])
        self.assertIn('用户新补充',self.store.read()['videos'][0]['transcript'])
    def test_review_only_skips_outline_and_detail_calls(self):
        self.build();self.ai.calls=[]
        build_knowledge(self.store,self.ai,'video',lambda m:None,review_only=True)
        self.assertEqual(len(self.ai.calls),1)
    def test_resume_after_review_timeout_keeps_completed_modules(self):
        generate=self.ai.harness_generate
        def timeout(prompt):
            if '独立的第二轮自查' in prompt:raise IntegrationError('超时')
            return generate(prompt)
        self.ai.harness_generate=timeout
        with self.assertRaises(IntegrationError):self.build()
        self.assertIsNone(self.store.read()['videos'][0]['knowledge'])
        self.ai.harness_generate=generate;self.ai.calls=[]
        result=self.build()
        self.assertEqual(len(self.ai.calls),1)
        self.assertEqual(len(result['modules']),2)
        self.assertFalse(any(v for k,v in self.ai.state.items() if k.startswith('knowledge-job-')))
    def test_model_change_does_not_resume_old_model_checkpoint(self):
        generate=self.ai.harness_generate
        def timeout(prompt):
            if '独立的第二轮自查' in prompt:raise IntegrationError('超时')
            return generate(prompt)
        self.ai.harness_generate=timeout
        with self.assertRaises(IntegrationError):self.build()
        read=self.ai.read
        self.ai.read=lambda name: {'model':{'provider':'new-provider','model':'different','reasoningEffort':'low'}} if name=='harness' else read(name)
        self.ai.harness_generate=generate;self.ai.calls=[]
        self.build()
        self.assertEqual(len(self.ai.calls),4)
        self.assertTrue(any('请把课程规划' in prompt for prompt in self.ai.calls))

    def test_review_batches_resume_without_repeating_completed_batch(self):
        self.ai.module_count=4;generate=self.ai.harness_generate;reviews=[]
        def interrupted(prompt):
            if '独立的第二轮自查' in prompt:
                group=json.loads(prompt.split('资料：\n')[-1])['draft']['modules']
                reviews.append([m['id'] for m in group])
                if len(reviews)==2:raise IntegrationError('第二批超时')
            return generate(prompt)
        self.ai.harness_generate=interrupted
        with self.assertRaises(IntegrationError):self.build()
        self.assertEqual(reviews,[['m1','m2'],['m3','m4']])
        self.ai.harness_generate=generate;self.ai.calls=[]
        result=self.build()
        self.assertEqual(len(self.ai.calls),1)
        self.assertEqual(len(result['modules']),4)
        self.assertIn('第 2 批',result['review']['summary'])
    def test_duplicate_module_or_malformed_concept_rejected(self):
        k=self.build();k['modules'][1]['id']=k['modules'][0]['id']
        with self.assertRaises(IntegrationError):validate_knowledge(k)
        k=self.build();k['modules'][0]['concepts']=['wrong']
        with self.assertRaises(IntegrationError):validate_knowledge(k)

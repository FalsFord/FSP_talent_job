import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.engine import Criteria
from app.main import adapt_report, app, definitions

class Reports(unittest.TestCase):
    def report(self, candidate, confidence=95, score=9):
        config = Criteria(min_grade='middle', min_experience_years=3, required_skills=['Python'], work_format='remote', salary_max=200000)
        criteria = definitions(config)
        result = {'scoring': {'summary': 'Проверка', 'evaluations': [dict(criterionKey=c['key'], confidence=confidence, applicantScore=score, evidence='Опыт из резюме', strengths=['Python'], gaps=[]) for c in criteria]}}
        return adapt_report(result, config, criteria, candidate)

    def test_unknown_never_definite_mismatch(self):
        self.assertEqual(self.report({}, score=0)['category'], 'review')
        self.assertTrue(all(r['status']=='unknown' for r in self.report({}, score=0)['criteria']))

    def test_verified_lower_grade_is_separate_category(self):
        report=self.report({'grade':'junior', 'grade_verified':True})
        self.assertEqual(report['category'], 'unsuitable')
        self.assertEqual(report['decision_owner'], 'employer')

    def test_complete_match(self):
        candidate=dict(grade='senior',grade_verified=True,experience_min=5,experience_max=5,skills=['Python'],work_formats=['remote'],salary_min=180000)
        self.assertEqual(self.report(candidate)['category'], 'suitable')
        self.assertEqual(self.report(candidate, confidence=40)['category'], 'review')

    def test_config_rejects_duplicate_and_reserved_keys(self):
        with self.assertRaises(ValueError):
            Criteria(reqcore_criteria=[dict(key='grade', name='Grade', description='', category='custom', maxScore=10, weight=10)])

    def test_minor_uncertainty_keeps_recommendation_but_major_gap_requires_review(self):
        candidate=dict(grade='middle',grade_verified=True,experience_min=5,experience_max=5,skills=['Python'],work_formats=['remote'])
        report=self.report(candidate)
        self.assertEqual(report['category'], 'suitable')
        self.assertEqual(next(r for r in report['criteria'] if r['key']=='salary')['status'], 'unknown')
        candidate['grade_verified']=False
        self.assertEqual(self.report(candidate)['category'], 'review')

    def test_service_token_required(self):
        os.environ['ATS_SERVICE_TOKEN']='test-service-token'
        with TestClient(app) as client:
            self.assertEqual(client.post('/evaluate', json={}).status_code,401)
            self.assertEqual(client.post('/auto-config',json={'title':'Python'},headers={'X-Service-Token':'test-service-token'}).status_code,200)

if __name__=='__main__': unittest.main()

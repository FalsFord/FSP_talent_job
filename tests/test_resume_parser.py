import unittest
from io import BytesIO
from app.services.resume_parser import extract_pdf, parse_text


def sample_pdf():
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer=PdfWriter();page=writer.add_blank_page(612,792)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    lines=['Name: Alex Ivanov','City: Moscow','Position: Python Developer','+7 999 123 45 67','alex@example.org','Work experience','January 2020 - December 2023','Example Company','Backend Developer','Built FastAPI services with PostgreSQL','Skills','Python Docker SQL','About me','Build reliable services.']
    stream=DecodedStreamObject();stream.set_data(('BT /F1 11 Tf 50 740 Td '+' '.join('('+line+') Tj 0 -14 Td' for line in lines)+' ET').encode())
    page[NameObject('/Contents')]=writer._add_object(stream)
    out=BytesIO();writer.write(out);return out.getvalue()


class ResumeTests(unittest.TestCase):
    def test_russian_sections_and_multiple_jobs(self):
        text='''Иванов Иван Петрович
Город: Казань
Должность: Backend разработчик
+7 (999) 123-45-67
ivan@example.org
Опыт работы — 4 года
Январь 2020 — Декабрь 2022
Компания А
Python разработчик
Разработка FastAPI и PostgreSQL.
Январь 2023 — настоящее время
Компания Б
Backend разработчик
Docker и Redis.
Ключевые навыки
Python, Java, JavaScript
Образование
Университет
Обо мне
Создаю надёжные сервисы.'''
        fields=parse_text(text)
        self.assertEqual(fields['name'],'Иван')
        self.assertEqual(fields['surname'],'Иванов')
        self.assertEqual(fields['city'],'Казань')
        self.assertEqual(fields['experience'],'4 года')
        self.assertEqual(len(fields['work_experience']),2)
        self.assertEqual(fields['work_experience'][0]['company'],'Компания А')
        self.assertNotIn('Университет',fields['work_experience'][1]['description'])
        self.assertIn('JavaScript',fields['tech'])
    def test_real_pdf_text_extraction(self):
        result=extract_pdf(sample_pdf())
        self.assertEqual(result['status'],'parsed')
        self.assertEqual(result['fields']['city'],'Moscow')
        self.assertEqual(result['fields']['work_experience'][0]['company'],'Example Company')
        self.assertEqual(result['fields']['contact_email'],'alex@example.org')
    def test_blank_encrypted_and_corrupt(self):
        from pypdf import PdfWriter
        writer=PdfWriter();writer.add_blank_page(100,100);out=BytesIO();writer.write(out)
        self.assertEqual(extract_pdf(out.getvalue())['status'],'no_text')
        writer.encrypt('password');out=BytesIO();writer.write(out)
        self.assertEqual(extract_pdf(out.getvalue())['status'],'encrypted')
        self.assertEqual(extract_pdf(b'%PDF-corrupt')['status'],'invalid')
    def test_skill_boundaries(self):
        fields=parse_text('JavaScript React PostgreSQL\nЛюблю путешествовать')
        self.assertNotIn('Java',fields['tech'])
        self.assertNotIn('SQL',fields['tech'])

if __name__=='__main__': unittest.main()

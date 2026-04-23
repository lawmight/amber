// Regression test for XML shader-effect field parsing.
//
// Specifically guards against a regression introduced during a cyclomatic-complexity
// refactor where Effect::parseFieldElement collapsed the EFFECT_FIELD_FONT branch into
// the StringField parser, causing <field type="font" ...> to load as a StringField.
//
// The test writes a tiny .xml shader-effect descriptor to a temp file, constructs an
// Effect from it (parent_clip = nullptr is acceptable for construction-only paths),
// and asserts the resulting field is a FontField with the correct type tag.

#include <QFile>
#include <QTemporaryDir>
#include <QtTest>

#include "core/appcontext.h"
#include "effects/effect.h"
#include "effects/effectfield.h"
#include "effects/effectfields.h"
#include "effects/effectrow.h"
#include "global/config.h"
#include "tests/test_appcontext_stub.h"

namespace {

QString WriteEffectXml(const QString& dir, const QString& filename, const QString& body) {
  const QString path = dir + "/" + filename;
  QFile f(path);
  if (!f.open(QFile::WriteOnly | QFile::Text)) return {};
  f.write(body.toUtf8());
  f.close();
  return path;
}

// Effect::parseEffectXml opens meta->filename verbatim (not path + "/" + filename),
// so the full absolute path goes in `filename`.
EffectMeta MakeMeta(const QString& full_xml_path) {
  EffectMeta em;
  em.name = "TestEffect";
  em.category = "Test";
  em.filename = full_xml_path;
  em.path = QString();
  em.tooltip = QString();
  em.internal = -1;
  em.type = EFFECT_TYPE_EFFECT;
  em.subtype = 0;
  return em;
}

}  // namespace

class TestEffectXmlParse : public QObject {
  Q_OBJECT

 private:
  TestAppContext stub_ctx_;
  QTemporaryDir tmpdir_;

 private slots:
  void initTestCase() {
    amber::app_ctx = &stub_ctx_;
    amber::CurrentConfig = {};
    QVERIFY(tmpdir_.isValid());
  }

  void cleanupTestCase() { amber::app_ctx = nullptr; }

  // Regression: <field type="font"> must construct a FontField, not a StringField.
  void fontFieldConstructsAsFontField() {
    const QString xml =
        "<effect>"
        "  <row name=\"font_row\">"
        "    <field type=\"font\" id=\"myfont\" default=\"Arial\"/>"
        "  </row>"
        "</effect>";
    const QString path = WriteEffectXml(tmpdir_.path(), "font_effect.xml", xml);
    QVERIFY(!path.isEmpty());

    EffectMeta meta = MakeMeta(path);
    Effect effect(nullptr, &meta);

    QCOMPARE(effect.row_count(), 1);
    EffectRow* r = effect.row(0);
    QVERIFY(r != nullptr);
    QCOMPARE(r->FieldCount(), 1);

    EffectField* f = r->Field(0);
    QVERIFY(f != nullptr);
    QCOMPARE(f->id(), QString("myfont"));
    QCOMPARE(static_cast<int>(f->type()), static_cast<int>(EffectField::EFFECT_FIELD_FONT));
    QVERIFY2(dynamic_cast<FontField*>(f) != nullptr,
             "Expected a FontField for type=\"font\" XML; got the wrong field subclass.");
    QVERIFY2(dynamic_cast<StringField*>(f) == nullptr,
             "FontField must not be a StringField subclass; widget factory dispatches on type().");
  }

  // Sanity check that the STRING and FILE branches still produce the right subclasses.
  void stringAndFileFieldStillCorrect() {
    const QString xml =
        "<effect>"
        "  <row name=\"r\">"
        "    <field type=\"string\" id=\"mystr\" default=\"hello\"/>"
        "    <field type=\"file\" id=\"myfile\" filename=\"/tmp/x\"/>"
        "  </row>"
        "</effect>";
    const QString path = WriteEffectXml(tmpdir_.path(), "string_file_effect.xml", xml);
    QVERIFY(!path.isEmpty());

    EffectMeta meta = MakeMeta(path);
    Effect effect(nullptr, &meta);

    QCOMPARE(effect.row_count(), 1);
    EffectRow* r = effect.row(0);
    QCOMPARE(r->FieldCount(), 2);

    EffectField* sf = r->Field(0);
    QCOMPARE(static_cast<int>(sf->type()), static_cast<int>(EffectField::EFFECT_FIELD_STRING));
    QVERIFY(dynamic_cast<StringField*>(sf) != nullptr);

    EffectField* ff = r->Field(1);
    QCOMPARE(static_cast<int>(ff->type()), static_cast<int>(EffectField::EFFECT_FIELD_FILE));
    QVERIFY(dynamic_cast<FileField*>(ff) != nullptr);
  }
};

QTEST_MAIN(TestEffectXmlParse)
#include "test_effect_xml_parse.moc"

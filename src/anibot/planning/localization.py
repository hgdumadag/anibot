from __future__ import annotations

from anibot.planning.schema import (
    DecisionRow,
    FarmingPlan,
    FarmingPlanRequest,
    GlossaryItem,
    MaoQuestion,
    MaterialChecklistGroup,
    PlanAction,
    PlanSection,
    RecordTemplate,
    TimelineItem,
)


def localize_plan(request: FarmingPlanRequest, plan: FarmingPlan) -> FarmingPlan:
    if request.language == "english":
        return plan.model_copy(update={"language": request.language})
    if request.language == "cebuano":
        return _localize_cebuano(request, plan)
    if request.language != "filipino":
        return plan.model_copy(update={"language": "english"})

    return plan.model_copy(
        update={
            "language": "filipino",
            "planning_basis": _planning_basis_fil(request),
            "warnings": _warnings_fil(request),
            "sections": _sections_fil(request, plan.sections),
            "timeline": _timeline_fil(request, plan.timeline),
            "glossary": _glossary_fil(),
            "decision_rows": _decision_rows_fil(request),
            "material_checklist": _material_checklist_fil(request),
            "record_templates": _record_templates_fil(),
            "mao_questions": _mao_questions_fil(request),
        }
    )


def _localize_cebuano(request: FarmingPlanRequest, plan: FarmingPlan) -> FarmingPlan:
    return plan.model_copy(
        update={
            "language": "cebuano",
            "planning_basis": _planning_basis_ceb(request),
            "warnings": _warnings_ceb(request),
            "sections": _sections_ceb(request, plan.sections),
            "timeline": _timeline_ceb(request, plan.timeline),
            "glossary": _glossary_ceb(),
            "decision_rows": _decision_rows_ceb(request),
            "material_checklist": _material_checklist_ceb(request),
            "record_templates": _record_templates_ceb(),
            "mao_questions": _mao_questions_ceb(request),
        }
    )


def _sections_fil(request: FarmingPlanRequest, sections: list[PlanSection]) -> list[PlanSection]:
    localized: list[PlanSection] = []
    for section in sections:
        title, guidance, actions = _section_content_fil(request, section.key)
        localized.append(
            section.model_copy(
                update={
                    "title": title,
                    "guidance": guidance,
                    "actions": actions,
                    "fallback_reason": _fallback_fil(section.fallback_reason),
                }
            )
        )
    return localized


def _section_content_fil(request: FarmingPlanRequest, key: str) -> tuple[str, list[str], list[PlanAction]]:
    crop = _crop_fil(request.crop)
    stored_crop = _stored_crop_fil(request.crop)
    farming_type = _farming_type_fil(request.farming_type)

    if key == "plan_summary":
        guidance = [
            f"Gumawa ng plano sa pagtatanim ng {crop} para sa {request.location_label} gamit ang {farming_type} na gabay kung mayroon.",
            f"Batayan ng plano: {_planning_basis_fil(request)}.",
            "Gamitin ito bilang gabay sa desisyon at ikumpirma sa Municipal Agriculture Office kung may kakaibang kondisyon sa bukid.",
        ]
        if request.field_notes:
            guidance.append(f"Isinaalang-alang na tala sa bukid: {request.field_notes}.")
        if _is_surigao_area(request):
            guidance.append("Para sa Marga o malapit sa Surigao City, ikumpirma sa MAO o lokal na magsasaka kung tugma ang petsa sa ulan, irigasyon, daluyan ng tubig, at baha.")
        return "Buod ng Plano", guidance, []

    if key == "current_concerns":
        selected = [concern for concern in request.concerns if concern != "none"] or ["none"]
        guidance = [
            f"Ipinasang alalahanin: {_concern_summary_fil(selected)}.",
            "Magsimula sa obserbasyon sa bukid at pagtatala bago maglagay ng pampataba, pestisidyo, o gumawa ng hindi na mababalik na aksyon.",
        ]
        if request.observation_notes.strip():
            guidance.append(f"Tala ng magsasaka: {_safe_user_text_fil(request.observation_notes)}.")
        for concern in selected:
            guidance.extend(_concern_guidance_fil(request, concern))
        return "Tugon sa Kasalukuyang Alalahanin", guidance, [_concern_action_fil(request, concern) for concern in selected]

    if key == "before_planting":
        guidance = [
            "Suriin muna kung ang lugar ay angkop bago maghanda ng lupa. Hanapin kung may malapit na kemikal, industriyal, basura, o panganib ng kontaminasyon.",
            "Kumuha ng sampol ng lupa bago maghanda ng bukid at gamitin ang resulta para sa desisyon sa sustansiya o soil amendment.",
            "Simpleng pagkuha ng sampol: lumakad nang zigzag, kumuha ng kaunting lupa sa ilang normal na bahagi, iwasan ang kakaibang lugar, paghaluin sa malinis na lalagyan, at dalhin sa MAO o rekomendadong laboratoryo.",
            "Ihanda ang bukid ayon sa hugis ng lupa, uri ng lupa, pattern ng ulan, pinagkukunan ng tubig, at daluyan ng tubig.",
            "Ayusin ang pilapil, kanal, at daluyan ng tubig bago magtanim, lalo na kung baha ang bukid o may inaasahang ulan.",
        ]
        if request.soil_condition == "dry":
            guidance.append("Kung masyadong tuyo ang lupa, unahin ang katiyakan ng tubig bago tapusin ang paghahanda ng lupa.")
        if request.soil_condition == "flooded":
            guidance.append("Kung baha ang bukid, patuyuin o patatagin muna ang lugar bago gumawa ng punlaan o magtanim.")
        return "Bago Magtanim", guidance, [
            PlanAction(task="Suriin ang bukid at kalapit na gamit ng lupa.", observe="Panganib ng kontaminasyon, mahinang daluyan ng tubig, o baha.", ask_for_help_if="Malapit ang bukid sa hinihinalang kemikal o basurang panganib."),
            PlanAction(task="Magpa-iskedyul ng soil test bago maglagay ng pampataba.", observe="Petsa ng soil test, resulta, at dating problema ng pananim.", ask_for_help_if="Walang soil test at dati nang mahina ang tubo ng halaman."),
            PlanAction(task="Ihanda ang pilapil, kanal, at pagkapantay ng bukid.", observe="Hindi pantay na tubig at baradong daloy.", ask_for_help_if="Hindi mailabas o maipon nang maayos ang tubig."),
        ]

    if key == "planting_establishment":
        guidance = [
            "Gumamit ng malinis at angkop na binhi o punla at ihanda ang punlaan o bukid bago magpatubo ng pananim.",
            "Hangarin ang pantay at malusog na tubo sa pamamagitan ng pagpapatag at pag-iwas sa mataas at mababang bahagi ng lupa.",
        ]
        if request.water_source == "rainfed":
            guidance.append("Para sa umaasa sa ulan, itugma ang pagtatanim sa aktuwal na halumigmig ng lupa at lokal na panahon.")
        else:
            guidance.append("Ikumpirma ang aktuwal na halumigmig, daluyan ng tubig, at kontrol sa tubig bago magtanim.")
        if request.planning_mode == "planning_to_plant":
            guidance.append("Huwag magtanim batay lang sa petsa; tiyaking kaya ng bukid ang halumigmig at pagdaloy ng tubig.")
        else:
            guidance.append("Dahil nakatanim na ang pananim, tutukan ang pantay na tubo, tubig, damo, at maagang palatandaan ng peste.")
        return "Pagtatanim at Pagpapatubo", guidance, [
            PlanAction(task="Suriin ang kondisyon ng binhi o punla.", observe="Mahina, hindi pantay, o kontaminadong materyal.", ask_for_help_if="Hindi tiyak ang kalidad ng binhi."),
            PlanAction(task="Ikumpirma ang pagkapantay ng bukid at kontrol sa tubig.", observe="Umpok, mababang bahagi, nakatayong tubig, o tuyong bahagi.", ask_for_help_if="Hindi mapanatili ang pantay na tubig sa bukid."),
        ]

    if key == "soil_fertility":
        amendment = "organikong soil amendment" if request.farming_type == "organic_traditional" else "pampataba o rehistradong organikong soil amendment"
        guidance = [
            "Ibatay ang desisyon sa sustansiya sa soil test o pagsusuri ng halaman, hindi sa hula.",
            f"Gamitin lamang ang rekomendadong kombinasyon at panahon ng {amendment} pagkatapos ng pagsusuri o gabay ng lokal na teknisyan.",
            f"Itago ang materyales sa sustansiya sa malinis, tuyo, at bahagyang mataas na lugar, hiwalay sa pestisidyo at sa pagpapatuyo o imbakan ng {stored_crop}.",
            "Itala ang pinagmulan, paghahanda, petsa, dami, paraan ng paglalagay, at taong responsable.",
        ]
        if request.farming_type == "organic_traditional":
            guidance.append(f"Para sa organiko/tradisyonal na {crop}, gumamit lamang ng pinapayagan at maayos na nabulok na organikong materyal o rehistradong organikong soil amendment.")
        else:
            guidance.append(f"Para sa karaniwang {crop}, gumamit lamang ng rehistradong kemikal na pampataba o rehistradong organikong soil amendment kung angkop.")
        return "Plano sa Lupa at Sustansiya", guidance, [
            PlanAction(task="Humiling o magpa-iskedyul ng soil testing.", observe="Petsa at resulta ng soil test.", ask_for_help_if="Kailangan mo ng payo sa sustansiya pero walang soil test."),
            PlanAction(task="Itago nang ligtas ang materyales sa sustansiya.", observe=f"Basa, tagas, halo-halong imbakan, o lapit sa {stored_crop}.", ask_for_help_if=f"Basa, walang label, o malapit sa pagpapatuyo ng {crop} ang materyales."),
        ]

    if key == "water_management":
        guidance = [
            "Planuhin ang pamamahala ng tubig ayon sa kondisyon ng bukid, pinagkukunan ng tubig, yugto ng pananim, at lokal na pattern ng ulan.",
            "Panatilihin ang kanal, pilapil, at daluyan para makapag-ipon o makapaglabas ng tubig kung kailangan.",
            "Suriin ang bukid pagkatapos ng malakas na ulan at sa tagtuyot; parehong kailangan ng mabilis na lokal na aksyon ang kakulangan at sobrang tubig.",
        ]
        if request.water_source == "rainfed":
            guidance.append("Dahil umaasa sa ulan ang bukid, mahalagang salik ang timing ng lokal na ulan sa pagtatanim at panganib sa tubig.")
        if request.water_source in {"rainfed", "unknown"}:
            guidance.append("Bago tapusin ang paghahanda ng lupa, itanong sa MAO o kalapit na magsasaka kung sapat ang inaasahang ulan sa linggo ng pagtatanim.")
        if request.soil_condition == "dry" or "water_shortage" in request.concerns:
            guidance.append("Sa tuyong kondisyon, iwasan ang hindi na mababalik na gawain sa bukid hanggang realistic ang tubig.")
        if request.soil_condition == "flooded" or "heavy_rain_flooding" in request.concerns:
            guidance.append("Sa panganib ng baha, unahin ang pag-check ng daluyan at humingi ng lokal na tulong kung lubog ang punla o pananim.")
        return "Plano sa Tubig", guidance, [
            PlanAction(task="Suriin ang pasukan at labasan ng tubig.", observe="Baradong kanal, sirang pilapil, bitak sa tuyong lupa, o nakatayong baha.", ask_for_help_if="Hindi maubos ang tubig pagkatapos ng ulan o hindi mapasukan ng irigasyon."),
            PlanAction(task="Suriin ang kondisyon ng bukid bawat linggo.", observe="Tuyo, basa, o bahang bahagi.", ask_for_help_if="Mabilis magbago ang kondisyon o may stress ang pananim."),
        ]

    if key == "pest_weed":
        guidance = [
            "Unahin ang Integrated Pest Management: magandang pagtubo, kalinisan ng bukid, regular na pagmamasid, at napapanahong hindi-kemikal na paraan.",
            "Bantayan ang damo, insekto, sintomas ng sakit, at kakaibang pinsala sa buong panahon.",
            "Gumamit lamang ng pestisidyo kung may sapat na dahilan at ayon sa rehistrasyon, label, PPE, at pre-harvest interval.",
            "Itala ang pagbili, paggamit, imbakan, at pagtatapon ng pestisidyo o agricultural chemical.",
        ]
        if request.farming_type == "organic_traditional":
            guidance.append(f"Para sa organiko/tradisyonal na {crop}, huwag gumamit ng kemikal na pestisidyo para sa nakaimbak na organikong {crop}; magtanong sa MAO bago gumawa ng paraan na maaaring makaapekto sa organic status.")
        else:
            guidance.append(f"Para sa karaniwang {crop}, hindi pipili ang app ng produktong pestisidyo; magtanong muna sa certified applicator o MAO bago pumili.")
        return "Pamamahala ng Peste, Sakit, at Damo", guidance, [
            PlanAction(task="Mag-scout sa bukid bawat linggo.", observe="Insekto, sira sa dahon, batik ng sakit, damo, o mahinang tubo.", ask_for_help_if="Kumakalat ang pinsala o hindi kilala ang peste."),
            PlanAction(task="Sundin ang ligtas na proseso bago gumamit ng pestisidyo.", observe="Pagkilala sa peste, lawak ng pinsala, label, rehistrasyon, PPE, imbakan, at pre-harvest interval.", ask_for_help_if="Hindi kilala ang peste, kumakalat ang pinsala, nawawala ang label, o hindi tiyak ang tamang gamit."),
        ]

    if key == "stage_checklist":
        guidance = [
            "Bago magtanim: suriin ang panganib sa bukid, ipa-test ang lupa, ayusin ang tubig, at ihanda ang malinis na binhi o punlaan.",
            "Pagtatanim hanggang maagang tubo: suriin ang pantay na tubo, tubig, damo, paninilaw, butas o sira sa dahon, suso, insekto, batik ng sakit, at mahinang punla.",
            "Aktibong paglaki: regular na bantayan ang sustansiya, tubig, peste, damo, pagdapa, at kumakalat na pinsala.",
            "Bago anihin: suriin ang kahinugan, iwasan ang kontaminasyon, at ihanda ang malinis na patuyuan at imbakan.",
        ]
        if request.planning_mode == "already_planted":
            guidance.insert(0, f"Magsimula sa kasalukuyang yugto: {request.current_stage}. Huwag ulitin ang naunang gawain maliban kung inirekomenda ng teknisyan.")
        return "Checklist Bawat Yugto", guidance, [
            PlanAction(task="Balikan ang checklist isang beses bawat linggo.", observe="Nalaktawang gawain o bagong panganib.", ask_for_help_if="Lumalala ang problema o wala sa checklist."),
            PlanAction(task="I-update ang tala pagkatapos ng bawat gawain.", observe="Petsa, materyal, kondisyon ng bukid, at tugon ng pananim.", ask_for_help_if="Hindi mo matiyak kung ano ang ginamit o kailan."),
        ]

    if key == "harvest_post_harvest":
        return "Ani at Pagkatapos ng Ani", [
            f"Bago anihin at hawakan pagkatapos ng ani, ilayo ang {stored_crop} sa lupa, maruming gamit, hayop, kemikal, at iba pang kontaminasyon.",
            "Gumamit ng malinis na gamit sa paghakot, pagpapatuyo, at imbakan.",
            f"Itago ang {crop} nang hiwalay sa pampataba, pestisidyo, treated pallets, o ibang posibleng kontaminasyon.",
            "Linisin ang imbakan bago gamitin, lalo na kung may hinalang bakas ng pestisidyo.",
        ], [
            PlanAction(task="Ihanda ang malinis na patuyuan at imbakan.", observe="Dumi, tagas, peste, lalagyan ng kemikal, o treated pallets.", ask_for_help_if="Maaaring may pestisidyo o kontaminasyon ang imbakan."),
            PlanAction(task=f"Hawakan ang inaning {crop} gamit ang malinis na materyales.", observe="Direktang dikit sa lupa o halo sa kontaminant.", ask_for_help_if="Walang malinis na patuyuan o panghakot."),
        ]

    if key == "records":
        return "Mga Talang Dapat Itago", [
            "Itala ang petsa ng pagtatanim, pinagmulan ng binhi, resulta ng soil test, materyal sa sustansiya, paggamit ng pestisidyo o agricultural chemical, obserbasyon sa peste, problema sa panahon, at resulta ng ani.",
            "Para sa pampataba o organikong soil amendment, itala ang pinagmulan, paghahanda, petsa, dami, paraan, at taong responsable.",
            "Para sa pestisidyo o agricultural chemical, itala ang pagbili, paggamit, imbakan, pagtatapon, pagsunod sa label, at pre-harvest interval.",
        ], [
            PlanAction(task="Isulat ang tala sa mismong araw ng gawain.", observe="Nawawalang petsa, materyal, o obserbasyon.", ask_for_help_if="Hindi mo matukoy kung anong input ang ginamit."),
        ]

    return "Babala at Paghingi ng Tulong", _warnings_fil(request), [
        PlanAction(task="Ipaalam agad ang malubha o hindi tiyak na problema.", observe="Mabilis kumalat na peste o sakit, hinihinalang kontaminasyon, baha, tagtuyot, o hindi tiyak na paggamit ng pestisidyo.", ask_for_help_if="May alinmang babala."),
    ]


def _timeline_fil(request: FarmingPlanRequest, timeline: list[TimelineItem]) -> list[TimelineItem]:
    if request.planning_mode == "already_planted":
        return [
            TimelineItem(
                period="Kasalukuyang linggo",
                approximate_date=f"Kasalukuyang yugto: {request.current_stage}",
                task="Magsimula sa pag-check ng bukid at pagtatala.",
                how_to_steps=[
                    "Lakarin ang gilid at gitnang bahagi ng bukid.",
                    "Itala ang tubig, damo, paninilaw, sira sa dahon, batik ng sakit, at hindi pantay na tubo.",
                    "Isulat ang kasalukuyang yugto at problema sa record template.",
                ],
                observe="Tubig, damo, palatandaan ng peste, paninilaw, batik ng sakit, pagdapa, at kumakalat na pinsala.",
                ask_for_help_if="Kumakalat ang pinsala, hindi makontrol ang tubig, o hindi tiyak ang yugto ng pananim.",
            )
        ]

    rows = []
    for item in timeline:
        period = _period_fil(item.period)
        rows.append(
            TimelineItem(
                period=period,
                approximate_date=_date_text_fil(item.approximate_date),
                task=_timeline_task_fil(period),
                how_to_steps=_timeline_steps_fil(period, request),
                observe=_timeline_observe_fil(period),
                ask_for_help_if=_timeline_help_fil(period),
            )
        )
    return rows


def _timeline_task_fil(period: str) -> str:
    tasks = {
        "4-6 linggo bago magtanim": "Bumisita sa MAO at ikumpirma ang lokal na plano sa pagtatanim.",
        "3-4 linggo bago magtanim": "Kumuha ng sampol ng lupa at suriin ang kontrol sa tubig.",
        "1-2 linggo bago magtanim": "Ihanda ang binhi, punlaan, gamit, daanan sa bukid, at manggagawa.",
        "Linggo ng pagtatanim": "Magtanim lamang kung kaya ng bukid ang gawain.",
        "Bawat linggo pagkatapos magtanim": "Mag-scout sa bukid bawat linggo.",
        "Bago anihin": "Ihanda ang malinis na patuyuan at imbakan.",
    }
    return tasks.get(period, "Sundin ang nakatakdang gawain at magtala.")


def _timeline_steps_fil(period: str, request: FarmingPlanRequest) -> list[str]:
    crop = _crop_fil(request.crop)
    if period == "4-6 linggo bago magtanim":
        steps = [
            "Dalhin sa MAO ang lokasyon, target na petsa ng pagtatanim, pinagkukunan ng tubig, at tala sa bukid.",
            "Itanong kung tugma ang timing sa lokal na cropping calendar at kondisyon ng tubig.",
            f"Ikumpirma ang rekomendadong variety ng {crop} at saan maaaring magpa-soil test.",
        ]
        if _is_surigao_area(request):
            steps.append("Itanong ang tungkol sa ulan, irigasyon, daluyan ng tubig, at bahain na bahagi sa Marga o Surigao City.")
        return steps
    if period == "3-4 linggo bago magtanim":
        return [
            "Lumakad nang zigzag sa bukid at kumuha ng kaunting lupa sa ilang normal na bahagi.",
            "Iwasan ang kakaibang bahagi tulad ng compost pile, nasunog na lugar, kanal, o gilid ng bukid.",
            "Paghaluin ang lupa sa malinis na lalagyan at dalhin sa MAO o rekomendadong laboratoryo.",
            "Suriin ang pilapil, kanal, at daluyan habang naghihintay ng gabay.",
        ]
    if period == "1-2 linggo bago magtanim":
        return [
            "Ihanda ang malinis na binhi o punla mula sa mapagkakatiwalaang pinagmulan.",
            "Ihanda ang punlaan o bukid at siguraduhing handa ang gamit at manggagawa.",
            "Ayusin ang daanan, pilapil, kanal, at daluyan bago ang araw ng pagtatanim.",
        ]
    if period == "Linggo ng pagtatanim":
        return [
            "Gamitin ang rekomendasyon ng MAO o teknisyan sa paraan ng pagtatanim, distansya, at dami ng binhi o punla.",
            "Magtanim sa pantay na bukid na may sapat na halumigmig at malinaw na hanay o taniman para madaling mag-check pagkatapos.",
            "Kung tuyo ang lupa, magpatubig o maghintay ng ulan; kung baha, paagasin muna.",
            "Itala ang petsa ng pagtatanim, pinagmulan ng binhi, paraan, halumigmig ng lupa, at bahaging tuyo o baha.",
        ]
    if period == "Bawat linggo pagkatapos magtanim":
        return [
            "Lakarin ang bukid isang beses bawat linggo, kasama ang gilid at gitnang bahagi.",
            "Suriin ang tubig, damo, paninilaw, butas o sira sa dahon, suso, insekto, batik ng sakit, mahinang tubo, at pagdapa.",
            "Kunan ng larawan ang kakaibang sintomas at tingnan kung kumakalat ang pinsala.",
        ]
    return [
        "Linisin ang patuyuan, sako, gamit sa paghakot, at imbakan.",
        f"Ilayo ang {_stored_crop_fil(request.crop)} sa lupa, hayop, pampataba, pestisidyo, maruming gamit, at treated pallets.",
        "Suriin ang pesticide record para sa pre-harvest interval bago anihin.",
    ]


def _timeline_observe_fil(period: str) -> str:
    if period == "4-6 linggo bago magtanim":
        return "Lokal na cropping calendar, katiyakan ng tubig, variety advice, at soil test options."
    if period == "3-4 linggo bago magtanim":
        return "Kahandaan ng soil sample, baradong kanal, sirang pilapil, bitak sa tuyong lupa, o baha."
    if period == "1-2 linggo bago magtanim":
        return "Kondisyon ng binhi, kahandaan ng punlaan, gamit, pagkapantay ng bukid, at kontrol sa tubig."
    if period == "Linggo ng pagtatanim":
        return "Aktuwal na distansya o dami ng binhi, halumigmig ng lupa, pantay na hanay, daluyan, at kondisyon ng binhi o punla."
    if period == "Bawat linggo pagkatapos magtanim":
        return "Tubig, damo, paninilaw, sira sa dahon, suso, insekto, batik ng sakit, hindi pantay na tubo, pagdapa, at kumakalat na pinsala."
    return "Malinis na patuyuan, malinis na imbakan, bakas ng peste, lalagyan ng kemikal, maruming sako, o treated pallets."


def _timeline_help_fil(period: str) -> str:
    if period == "4-6 linggo bago magtanim":
        return "Hindi tugma ang target na petsa sa lokal na tubig o cropping conditions."
    if period == "3-4 linggo bago magtanim":
        return "Hindi makakuha ng soil testing guidance o hindi kayang mag-ipon o maglabas ng tubig ang bukid."
    if period == "1-2 linggo bago magtanim":
        return "Hindi tiyak ang kalidad ng binhi o hindi matatapos ang paghahanda ng bukid."
    if period == "Linggo ng pagtatanim":
        return "Hindi alam ang rekomendadong distansya o dami ng binhi, hindi tiyak ang kalidad ng binhi, o tuyo, baha, hindi pantay, o hindi umaagos ang bukid."
    if period == "Bawat linggo pagkatapos magtanim":
        return "Hindi kilala ang peste, kumakalat ang pinsala, lumalala ang paninilaw, o may stress sa tubig."
    return "Maaaring kontaminado ang patuyuan o imbakan, o hindi tiyak ang waiting time ng pestisidyo."


def _glossary_fil() -> list[GlossaryItem]:
    return [
        GlossaryItem(term="Pilapil", explanation="Nakataas na lupa sa paligid ng bukid na tumutulong mag-ipon o gumabay ng tubig."),
        GlossaryItem(term="Punlaan", explanation="Maliit na inihandang lugar kung saan pinatutubo ang punla bago ilipat."),
        GlossaryItem(term="IPM", explanation="Pamamahala ng peste na nagsisimula sa pag-check at pag-iwas, hindi agad pag-spray."),
        GlossaryItem(term="Pre-harvest interval", explanation="Kinakailangang paghihintay pagkatapos gumamit ng pestisidyo bago mag-ani."),
        GlossaryItem(term="Soil amendment", explanation="Materyal na idinadagdag upang mapabuti ang lupa, gaya ng compost o apog, kung angkop at inirekomenda."),
    ]


def _decision_rows_fil(request: FarmingPlanRequest) -> list[DecisionRow]:
    crop = _crop_fil(request.crop)
    rows = [
        DecisionRow(situation="Masyadong tuyo ang bukid bago magtanim", first_check="Suriin ang pinagkukunan ng tubig at kalapit na bukid.", what_to_do_next="Huwag ituloy ang huling paghahanda ng lupa hanggang realistic ang tubig.", contact_mao_if="Hindi tiyak ang tubig o nagpapatuloy ang tuyong kondisyon."),
        DecisionRow(situation="Baha ang bukid at hindi umaagos", first_check="Suriin ang daluyan, kanal, at sirang pilapil.", what_to_do_next="Linisin ang daluyan kung ligtas at ipagpaliban ang punlaan o pagtatanim.", contact_mao_if="Hindi maubos ang tubig o lubog ang punla."),
        DecisionRow(situation="Nanininilaw ang dahon", first_check="Suriin ang tubig at kung kumakalat ang paninilaw.", what_to_do_next="Itala ang sintomas at humingi ng soil o plant-based guidance bago maglagay ng sustansiya.", contact_mao_if="Kumakalat ang paninilaw, mahina ang tubo, o walang soil test."),
        DecisionRow(situation="May insekto, suso, o sira sa dahon", first_check="Kilalanin ang peste at tingnan kung kumakalat ang pinsala.", what_to_do_next="Huwag agad mag-spray; kumuha ng larawan at obserbahan ang lawak ng pinsala.", contact_mao_if="Hindi kilala ang peste o kumakalat ang pinsala."),
        DecisionRow(situation="Dumarami ang damo", first_check=f"Suriin kung nakikipag-agawan ang damo sa batang {crop}.", what_to_do_next="Kumilos nang maaga gamit ang lokal na payo sa weed management at magtala.", contact_mao_if=f"Hindi ka sigurado kung damo ang halaman o napipigil ang tubo ng {crop}."),
        DecisionRow(situation="Marumi ang anihan o imbakan", first_check="Hanapin ang lupa, peste, hayop, lalagyan ng kemikal, maruming gamit, o treated pallets.", what_to_do_next="Linisin o pumili ng ibang patuyuan at imbakan bago anihin.", contact_mao_if="May hinalang pestisidyo o kontaminasyon."),
    ]
    if request.water_source in {"rainfed", "unknown"}:
        rows.insert(0, DecisionRow(situation="Hindi tiyak ang ulan bago magtanim", first_check="Magtanong sa kalapit na magsasaka at MAO tungkol sa lokal na timing ng ulan.", what_to_do_next="Ipagpaliban ang hindi na mababalik na gawain hanggang realistic ang halumigmig sa pagtatanim.", contact_mao_if="Walang maaasahang tubig para sa planong linggo."))
    return rows


def _material_checklist_fil(request: FarmingPlanRequest) -> list[MaterialChecklistGroup]:
    crop = _crop_fil(request.crop)
    return [
        MaterialChecklistGroup(category="Binhi", items=[f"Rekomendadong variety ng {crop}", "Malinis na pinagmulan ng binhi", "Lalagyan ng binhi o punla"]),
        MaterialChecklistGroup(category="Gamit sa bukid", items=["Araro o hand tractor access", "Gamit sa pagpapatag", "Bota", "Pananda sa bukid"]),
        MaterialChecklistGroup(category="Kontrol sa tubig", items=["Gamit sa paglilinis ng kanal", "Materyales sa pag-aayos ng pilapil", "Daanan ng tubig"]),
        MaterialChecklistGroup(category="Talaan", items=["Notebook", "Bolpen", "Phone camera para sa larawan ng bukid"]),
        MaterialChecklistGroup(category="Kaligtasan", items=["Guwantes", "Mask o PPE kapag hahawak ng kemikal", "Label at imbakan para sa inputs"]),
        MaterialChecklistGroup(category="Pagkatapos ng ani", items=["Malinis na sako", "Malinis na drying mat", "Malinis na imbakan", "Malinis na panghakot"]),
    ]


def _record_templates_fil() -> list[RecordTemplate]:
    return [
        RecordTemplate(title="Tala ng Gawain sa Bukid", columns=["Petsa", "Gawain", "Kondisyon ng bukid", "Input na ginamit", "Dami", "Obserbasyon", "Responsable"], sample_row=["Hunyo 15", "Pagtatanim", "Basa at pantay", "Binhi", "Isulat ang aktuwal na dami", "Mabuti o hindi pantay", "Pangalan"]),
        RecordTemplate(title="Tala ng Pestisidyo o Agricultural Chemical", columns=["Petsa", "Peste/problema", "Produktong ginamit", "Nasunod ang label?", "Gumamit ng PPE?", "Pre-harvest interval", "Sino ang nagpayo?"], sample_row=["Isulat ang petsa", "Hindi kilalang insekto", "Wala hanggat walang payo", "Oo/Hindi", "Oo/Hindi", "Isulat ang nasa label", "MAO o teknisyan"]),
        RecordTemplate(title="Lingguhang Obserbasyon sa Bukid", columns=["Petsa", "Kondisyon ng tubig", "Damo", "Palatandaan ng peste", "Paninilaw/batik", "May larawan?", "Susunod na aksyon"], sample_row=["Isulat ang petsa", "Tuyo/basa/baha", "Kaunti/katamtaman/marami", "Ilarawan ang senyales", "Ilarawan ang sintomas", "Oo/Hindi", "Bantayan o magtanong sa MAO"]),
    ]


def _mao_questions_fil(request: FarmingPlanRequest) -> list[MaoQuestion]:
    crop = _crop_fil(request.crop)
    questions = [
        MaoQuestion(topic="Petsa ng pagtatanim at tubig", question=f"Tugma ba ang pagtatanim sa paligid ng {request.target_planting_date} sa lokal na kalendaryo ng {crop}, ulan, irigasyon, at daluyan ng tubig para sa {request.location_label}?"),
        MaoQuestion(topic="Soil testing", question="Saan ko dadalhin ang pinagsamang soil sample, at sino ang makakatulong magsalin ng resulta sa schedule ng pampataba o amendment?"),
        MaoQuestion(topic="Binhi o variety", question=f"Aling variety ng {crop} at malinis na seed source ang rekomendado para sa kondisyon ng bukid at tubig?"),
    ]
    if _is_surigao_area(request):
        questions[0] = MaoQuestion(topic="Petsa ng pagtatanim at tubig", question=f"Para sa Marga o malapit sa Surigao City, tugma ba ang pagtatanim sa paligid ng {request.target_planting_date} sa karaniwang ulan, irigasyon, daluyan, at baha?")
    if {"pests", "weeds", "poor_growth"} & set(request.concerns):
        questions.append(MaoQuestion(topic="Kontak para sa problema sa bukid", question="Kung makakita ako ng insekto, suso, damo, butas sa dahon, paninilaw, o batik ng sakit, sino ang dapat tumukoy bago gumamit ng pestisidyo o sustansiya?"))
    if "harvest_post_harvest" in request.concerns:
        questions.append(MaoQuestion(topic="Pagkatapos ng ani", question="Anong lokal na paraan sa pagpapatuyo at imbakan ang dapat sundin para maiwasan ang kontaminasyon?"))
    return questions


def _warnings_fil(request: FarmingPlanRequest) -> list[str]:
    warnings = [
        "Ang planong ito ay gabay sa desisyon. Hindi nito hinuhulaan ang ani at hindi nito pinapalitan ang payo ng lokal na teknisyan.",
    ]
    if "pests" in request.concerns:
        warnings.append("Kung hindi kilala ang peste o kumakalat ang pinsala, kumonsulta sa MAO bago gumamit ng pestisidyo.")
    if "fertilizer_nutrient" in request.concerns or "poor_growth" in request.concerns:
        warnings.append("Huwag hulaan ang dami ng sustansiya. Gumamit ng soil o plant-based analysis at gabay ng lokal na teknisyan.")
    if request.soil_condition == "flooded" or "heavy_rain_flooding" in request.concerns:
        warnings.append(f"Mabilis makasira ang baha sa {_crop_fil(request.crop)}. Humingi ng lokal na tulong kung hindi maubos ang tubig o lubog ang halaman.")
    if request.soil_condition == "dry" or "water_shortage" in request.concerns:
        warnings.append("Kailangan ng lokal na plano sa tubig kapag tuyo ang bukid bago gumawa ng hindi na mababalik na gawain.")
    return warnings


def _fallback_fil(value: str | None) -> str | None:
    if not value:
        return value
    if "Unsupported crop" in value:
        return "Hindi suportado ang pananim sa Phase 1."
    return "Kulang ang nahanap na source-backed evidence; ikumpirma sa MAO."


def _planning_basis_fil(request: FarmingPlanRequest) -> str:
    if request.planning_mode == "planning_to_plant":
        return f"nagpaplanong magtanim; target na petsa: {request.target_planting_date}"
    return f"nakatanim na; kasalukuyang yugto: {request.current_stage}"


def _period_fil(value: str) -> str:
    return {
        "4-6 weeks before planting": "4-6 linggo bago magtanim",
        "3-4 weeks before planting": "3-4 linggo bago magtanim",
        "1-2 weeks before planting": "1-2 linggo bago magtanim",
        "Planting week": "Linggo ng pagtatanim",
        "Weekly after planting": "Bawat linggo pagkatapos magtanim",
        "Before harvest": "Bago anihin",
    }.get(value, value)


def _date_text_fil(value: str) -> str:
    replacements = {
        "Relative to target planting date": "Batay sa target na petsa ng pagtatanim",
        "Target week": "Target na linggo",
        "From planting until harvest": "Mula pagtatanim hanggang ani",
        "Several weeks before expected harvest": "Ilang linggo bago ang inaasahang ani",
        "January": "Enero",
        "February": "Pebrero",
        "March": "Marso",
        "April": "Abril",
        "May": "Mayo",
        "June": "Hunyo",
        "July": "Hulyo",
        "August": "Agosto",
        "September": "Setyembre",
        "October": "Oktubre",
        "November": "Nobyembre",
        "December": "Disyembre",
    }
    text = value
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _concern_summary_fil(concerns: list[str]) -> str:
    return ", ".join(_concern_label_fil(concern) for concern in concerns)


def _concern_label_fil(concern: str) -> str:
    return {
        "pests": "peste",
        "weeds": "damo",
        "poor_growth": "mahinang tubo",
        "fertilizer_nutrient": "alalahanin sa pampataba o sustansiya",
        "water_shortage": "kakulangan sa tubig",
        "heavy_rain_flooding": "malakas na ulan o baha",
        "harvest_post_harvest": "ani o pagkatapos ng ani",
        "none": "walang urgent na alalahanin",
    }.get(concern, concern.replace("_", " "))


def _concern_guidance_fil(request: FarmingPlanRequest, concern: str) -> list[str]:
    crop = _crop_fil(request.crop)
    if concern == "pests":
        return [
            "Para sa peste: kilalanin muna ang peste, tingnan kung kumakalat ang pinsala, at kumuha ng malinaw na larawan ng apektadong dahon, tangkay, o halaman.",
            "Huwag agad mag-spray o pumili ng pestisidyo mula sa app; magtanong sa MAO o kwalipikadong applicator kung hindi tiyak ang peste o paggamit ng pestisidyo.",
        ]
    if concern == "weeds":
        return [
            f"Para sa damo: tingnan kung nakikipag-agawan ang damo sa batang {crop}, lalo na sa gilid, basang bahagi, at manipis ang tubo.",
            "Kumilos nang maaga gamit ang lokal na payo sa weed management at itala ang ginamit na paraan.",
        ]
    if concern == "poor_growth":
        return [
            "Para sa mahinang tubo: ihambing ang mahina at malusog na bahagi, pagkatapos suriin ang tubig, pantay na tubo, paninilaw, peste, at batik ng sakit.",
            "Huwag hulaan ang sanhi o maglagay ng sustansiya bilang trial; dalhin ang tala o larawan sa MAO kung nagpapatuloy ang mahinang tubo.",
        ]
    if concern == "fertilizer_nutrient":
        return [
            "Para sa alalahanin sa pampataba o sustansiya: gumamit ng soil o plant-based analysis bago magdesisyon sa materyal, timing, o dami.",
            "Itala ang dating paggamit ng pampataba o amendment, tugon ng pananim, at anumang paninilaw o hindi pantay na tubo bago humingi ng lokal na gabay.",
        ]
    if concern == "water_shortage":
        return [
            "Para sa kakulangan sa tubig: suriin ang pinagkukunan ng tubig, kanal, pilapil, kalapit na bukid, at kung masyadong tuyo ang lupa para sa susunod na gawain.",
            "Ipagpaliban ang hindi na mababalik na gawain kung hindi realistic ang tubig.",
        ]
    if concern == "heavy_rain_flooding":
        return [
            "Para sa malakas na ulan o baha: suriin ang daluyan, kanal, sirang pilapil, at kung lubog ang punla o nakatayong pananim.",
            "Humingi agad ng lokal na tulong kung hindi maubos ang tubig o nananatiling lubog ang halaman.",
        ]
    if concern == "harvest_post_harvest":
        return [
            f"Para sa ani o pagkatapos ng ani: ilayo ang {_stored_crop_fil(request.crop)} sa lupa, maruming gamit, hayop, lalagyan ng kemikal, at treated pallets.",
            "Ihanda ang malinis na patuyuan, panghakot, at imbakan bago magsimula ang ani.",
        ]
    return [
        "Walang urgent na alalahanin ang pinili. Gamitin ang lingguhang checklist para bantayan ang tubig, damo, peste, paninilaw, batik ng sakit, at hindi pantay na tubo.",
    ]


def _concern_action_fil(request: FarmingPlanRequest, concern: str) -> PlanAction:
    crop = _crop_fil(request.crop)
    if concern == "pests":
        return PlanAction(task="Tugunan ngayon ang alalahanin sa peste.", observe="Pagkakakilanlan ng peste, bilang ng apektadong halaman, larawan, at kung kumakalat ang pinsala.", ask_for_help_if="Hindi kilala ang peste, kumakalat ang pinsala, o pinag-iisipan ang pestisidyo.")
    if concern == "weeds":
        return PlanAction(task="I-map ang damo sa bukid.", observe=f"Uri ng damo, dami ng damo, pagpigil sa batang {crop}, at basang o manipis ang tubo na bahagi.", ask_for_help_if=f"Hindi ka sigurado kung damo ang halaman o napipigil ang tubo ng {crop}.")
    if concern == "poor_growth":
        return PlanAction(task="Ihambing ang mahina at malusog na bahagi ng pananim.", observe="Tubig, paninilaw, peste, batik ng sakit, puwang sa tanim, at kamakailang gawain sa bukid.", ask_for_help_if="Kumakalat ang mahinang tubo, lumalala ang paninilaw, o walang soil o plant analysis.")
    if concern == "fertilizer_nutrient":
        return PlanAction(task="Maghanda para sa soil o plant-based nutrient guidance.", observe="Status ng soil test, dating paggamit ng sustansiya, paninilaw, hindi pantay na tubo, at tugon ng pananim.", ask_for_help_if="Kailangan mo ng payo sa sustansiya pero walang soil test o plant-based analysis.")
    if concern == "water_shortage":
        return PlanAction(task="Suriin kung sapat ang tubig bago ang susunod na gawain.", observe="Katiyakan ng tubig, daloy sa kanal, bitak sa tuyong lupa, kondisyon ng kalapit na bukid, at halumigmig ng lupa.", ask_for_help_if="Walang maaasahang tubig o nagpapatuloy ang tuyong kondisyon.")
    if concern == "heavy_rain_flooding":
        return PlanAction(task="Suriin ang daluyan at lubog na bahagi ng pananim.", observe="Baradong daluyan, sirang pilapil, lalim ng tubig, lubog na punla, at nakatayong tubig.", ask_for_help_if="Hindi maubos ang tubig o nananatiling lubog ang halaman.")
    if concern == "harvest_post_harvest":
        return PlanAction(task="Suriin ang anihan, patuyuan, at imbakan.", observe="Dikit sa lupa, peste, tagas, maruming sako, lalagyan ng kemikal, o treated pallets.", ask_for_help_if="Walang malinis na patuyuan o imbakan, o may hinalang kontaminasyon.")
    return PlanAction(task="Gamitin ang lingguhang field check.", observe="Tubig, damo, peste, paninilaw, batik ng sakit, hindi pantay na tubo, at tala sa bukid.", ask_for_help_if="May lumitaw, lumala, o hindi tiyak na problema.")


def _safe_user_text_fil(value: str) -> str:
    text = " ".join(value.split())
    for term in ("capital", "budget", "cost", "price"):
        text = text.replace(term, "[tinanggal na money term]")
        text = text.replace(term.title(), "[tinanggal na money term]")
        text = text.replace(term.upper(), "[tinanggal na money term]")
    return text


def _sections_ceb(request: FarmingPlanRequest, sections: list[PlanSection]) -> list[PlanSection]:
    localized: list[PlanSection] = []
    for section in sections:
        title, guidance, actions = _section_content_ceb(request, section.key)
        localized.append(
            section.model_copy(
                update={
                    "title": title,
                    "guidance": guidance,
                    "actions": actions,
                    "fallback_reason": _fallback_ceb(section.fallback_reason),
                }
            )
        )
    return localized


def _section_content_ceb(request: FarmingPlanRequest, key: str) -> tuple[str, list[str], list[PlanAction]]:
    crop = _crop_ceb(request.crop)
    stored_crop = _stored_crop_ceb(request.crop)
    farming_type = _farming_type_ceb(request.farming_type)

    if key == "plan_summary":
        guidance = [
            f"Paghimo og plano sa pagpananom og {crop} para sa {request.location_label} gamit ang {farming_type} nga giya kung naa.",
            f"Basehan sa plano: {_planning_basis_ceb(request)}.",
            "Gamita kini isip giya sa desisyon ug ikumpirma sa Municipal Agriculture Office kung naay dili kasagarang kondisyon sa uma.",
        ]
        if request.field_notes:
            guidance.append(f"Gikonsiderar nga tala sa uma: {request.field_notes}.")
        if _is_surigao_area(request):
            guidance.append("Para sa Marga o duol sa Surigao City, ikumpirma sa MAO o lokal nga mag-uuma kung ang petsa angay sa ulan, irigasyon, drainage, ug baha.")
        return "Kinatibuk-ang Plano", guidance, []

    if key == "current_concerns":
        selected = [concern for concern in request.concerns if concern != "none"] or ["none"]
        guidance = [
            f"Gisumiter nga kabalaka: {_concern_summary_ceb(selected)}.",
            "Sugdi sa pag-obserbar sa uma ug pagsulat sa record sa dili pa magbutang og abono, pestisidyo, o mohimo og aksyon nga lisod na usbon.",
        ]
        if request.observation_notes.strip():
            guidance.append(f"Tala sa mag-uuma: {_safe_user_text_ceb(request.observation_notes)}.")
        for concern in selected:
            guidance.extend(_concern_guidance_ceb(request, concern))
        return "Tubag sa Kasamtangang Kabalaka", guidance, [_concern_action_ceb(request, concern) for concern in selected]

    if key == "before_planting":
        guidance = [
            "Susiha una kung ang lugar angay sa pagpananom. Tan-awa kung naay duol nga kemikal, industriya, basura, o posibleng kontaminasyon.",
            "Kuhaa ang sample sa yuta sa dili pa andamon ang uma ug gamita ang resulta para sa desisyon sa sustansiya o soil amendment.",
            "Simple nga soil sample: lakaw og zigzag, kuha og gamay nga yuta sa daghang normal nga parte, likayi ang lahi nga spots, sagola sa limpyo nga sudlanan, ug dad-a sa MAO o rekomendadong laboratoryo.",
            "Andama ang uma base sa porma sa yuta, klase sa yuta, ulan, tinubdan sa tubig, ug drainage.",
            "Ayuhon ang pilapil, kanal, ug agianan sa tubig sa dili pa magtanom, labi na kung baha ang uma o naay gipaabot nga ulan.",
        ]
        if request.soil_condition == "dry":
            guidance.append("Kung uga kaayo ang yuta, unaha ang kasigurohan sa tubig sa dili pa humanon ang pag-andam sa uma.")
        if request.soil_condition == "flooded":
            guidance.append("Kung baha ang uma, paagasa o pa-stabilize una ang lugar sa dili pa magpunlaan o magtanom.")
        return "Sa Dili Pa Magtanom", guidance, [
            PlanAction(task="Susiha ang uma ug palibot nga gamit sa yuta.", observe="Kontaminasyon, huyang nga drainage, o baha.", ask_for_help_if="Duol ang uma sa posibleng kemikal o basura nga peligro."),
            PlanAction(task="Magpa-iskedyul og soil test sa dili pa mag-abono.", observe="Petsa sa soil test, resulta, ug daang problema sa tanom.", ask_for_help_if="Walay soil test ug kaniadto huyang ang tubo sa tanom."),
            PlanAction(task="Andama ang pilapil, kanal, ug pagpatag sa uma.", observe="Dili patas nga tubig ug barado nga agianan.", ask_for_help_if="Dili maayo ang paggawas o pagpundo sa tubig."),
        ]

    if key == "planting_establishment":
        guidance = [
            "Gamit og limpyo ug angay nga binhi o seedling, ug andama ang punlaan o uma sa dili pa patuboon ang tanom.",
            "Tumonga ang himsog ug patas nga pagtubo pinaagi sa pagpatag sa uma ug paglikay sa taas ug ubos nga parte.",
            "Ayaw magtanom base lang sa kalendaryo; siguroa nga ang yuta naay angay nga kaumog ug drainage.",
        ]
        if request.water_source == "rainfed":
            guidance.append("Kung nagsalig sa ulan, itunong ang pagpananom sa aktuwal nga kaumog sa uma ug lokal nga panahon.")
        if request.planning_mode == "already_planted":
            guidance.append("Kay nakatanom na, tutuki ang patas nga tubo, kondisyon sa tubig, sagbot, ug sayo nga timailhan sa peste.")
        return "Pagpananom ug Pagpatubo", guidance, [
            PlanAction(task="Susiha ang kondisyon sa binhi o seedling.", observe="Huyang, dili patas, o kontaminado nga materyal.", ask_for_help_if="Dili sigurado ang kalidad sa binhi."),
            PlanAction(task="Ikumpirma ang pagkapatas sa uma ug kontrol sa tubig.", observe="Bungtod, ubos nga parte, nagtindog nga tubig, o uga nga parte.", ask_for_help_if="Dili mapadayon ang patas nga tubig sa uma."),
        ]

    if key == "soil_fertility":
        amendment = "organikong soil amendment" if request.farming_type == "organic_traditional" else "abono o rehistradong organikong soil amendment"
        guidance = [
            "Ibase ang desisyon sa sustansiya sa soil test o plant-based analysis, dili sa tagna.",
            f"Gamiton lang ang rekomendadong kombinasyon ug timing sa {amendment} human sa analysis o giya sa lokal nga teknisyan.",
            f"Itago ang materyales sa sustansiya sa limpyo, uga, ug medyo taas nga lugar, layo sa pestisidyo ug sa pagpauga o storage sa {stored_crop}.",
            "Isulat ang gigikanan, pag-andam, petsa, gidaghanon, paagi sa paggamit, ug kinsa ang responsable.",
        ]
        return "Plano sa Yuta ug Sustansiya", guidance, [
            PlanAction(task="Mangayo o magpa-iskedyul og soil testing.", observe="Petsa ug resulta sa soil test.", ask_for_help_if="Nagkinahanglan og nutrient advice pero walay soil test."),
            PlanAction(task="Itago og luwas ang materyales sa sustansiya.", observe=f"Basa, naay tagas, gisagol sa lain, o duol sa {stored_crop}.", ask_for_help_if=f"Basa, walay label, o duol sa pagpauga sa {crop} ang materyales."),
        ]

    if key == "water_management":
        guidance = [
            "Planuhon ang tubig base sa kondisyon sa uma, tinubdan sa tubig, yugto sa tanom, ug lokal nga ulan.",
            "Panatilihon ang kanal, pilapil, ug drainage aron makapundo o makapagawas og tubig kung kinahanglan.",
            "Susiha ang uma human sa kusog nga ulan ug panahon sa kauga; pareho nga kinahanglan og dali nga lokal nga aksyon.",
        ]
        if request.water_source == "rainfed":
            guidance.append("Tungod kay nagsalig sa ulan ang uma, importante ang timing sa lokal nga ulan sa pagtanom ug water risk.")
        if request.soil_condition == "dry" or "water_shortage" in request.concerns:
            guidance.append("Kung uga, likayi ang lisod-usbon nga trabaho sa uma hangtod realistic ang tubig.")
        if request.soil_condition == "flooded" or "heavy_rain_flooding" in request.concerns:
            guidance.append("Kung naay baha, unaha ang drainage check ug pangayo og lokal nga tabang kung lubog ang seedling o tanom.")
        return "Plano sa Tubig", guidance, [
            PlanAction(task="Susiha ang sulod ug gawas sa tubig.", observe="Barado nga kanal, guba nga pilapil, liki sa uga nga yuta, o nagtindog nga baha.", ask_for_help_if="Dili mahubas ang tubig human sa ulan o dili kasulod ang irigasyon."),
            PlanAction(task="Susiha ang kondisyon sa uma kada semana.", observe="Uga, basa, o baha nga parte.", ask_for_help_if="Paspas mausab ang kondisyon o naay stress ang tanom."),
        ]

    if key == "pest_weed":
        guidance = [
            "Unaha ang Integrated Pest Management: maayong pagtubo, kalimpyo sa uma, regular nga pagtan-aw, ug tukmang dili-kemikal nga paagi.",
            "Bantayi ang sagbot, insekto, sintomas sa sakit, ug lahi nga kadaot sa tibuok season.",
            "Gamit og pestisidyo lang kung klaro ang rason ug sumala sa rehistrasyon, label, PPE, ug pre-harvest interval.",
            "Isulat ang pagpalit, paggamit, storage, ug disposal sa pestisidyo o agricultural chemical.",
        ]
        if request.farming_type == "organic_traditional":
            guidance.append(f"Para sa organiko/tradisyonal nga {crop}, ayaw gamit og kemikal nga pestisidyo sa stored organic {crop}; pangutana sa MAO una.")
        else:
            guidance.append(f"Para sa conventional nga {crop}, dili mopili ang app og pestisidyo; pangutana sa certified applicator o MAO una.")
        return "Pagdumala sa Peste, Sakit, ug Sagbot", guidance, [
            PlanAction(task="Mag-scout sa uma kada semana.", observe="Insekto, kadaot sa dahon, spots sa sakit, sagbot, o huyang nga tubo.", ask_for_help_if="Mokalat ang kadaot o dili mailhan ang peste."),
            PlanAction(task="Sunda ang luwas nga proseso sa dili pa mogamit og pestisidyo.", observe="Pag-ila sa peste, kadako sa kadaot, label, rehistrasyon, PPE, storage, ug pre-harvest interval.", ask_for_help_if="Dili mailhan ang peste, mokalat ang kadaot, nawala ang label, o dili sigurado ang paggamit."),
        ]

    if key == "stage_checklist":
        guidance = [
            "Sa dili pa magtanom: susiha ang peligro sa uma, ipa-test ang yuta, ayuha ang tubig, ug andama ang limpyo nga binhi o punlaan.",
            "Pagpananom hangtod sayo nga tubo: susiha ang patas nga tubo, tubig, sagbot, pagpanilaw, buslot o kadaot sa dahon, suso, insekto, spots sa sakit, ug huyang nga seedling.",
            "Aktibong pagtubo: bantayi ang sustansiya, tubig, peste, sagbot, pagdapa, ug mokalat nga kadaot.",
            "Sa dili pa anihon: susiha ang kahinog, likayi ang kontaminasyon, ug andama ang limpyo nga patuyuan ug storage.",
        ]
        if request.planning_mode == "already_planted":
            guidance.insert(0, f"Sugdi sa kasamtangang yugto: {request.current_stage}. Ayaw balika ang naunang trabaho gawas kung giingon sa teknisyan.")
        return "Checklist Kada Yugto", guidance, [
            PlanAction(task="Balika ang checklist kausa kada semana.", observe="Nalaktawan nga trabaho o bag-ong peligro.", ask_for_help_if="Nagkagrabe ang problema o wala sa checklist."),
            PlanAction(task="I-update ang record human sa matag trabaho.", observe="Petsa, materyal, kondisyon sa uma, ug tubag sa tanom.", ask_for_help_if="Dili ka sigurado unsay gigamit o kanus-a."),
        ]

    if key == "harvest_post_harvest":
        return "Ani ug Human sa Ani", [
            f"Sa dili pa anihon ug human sa ani, ilayo ang {stored_crop} sa yuta, hugaw nga gamit, hayop, kemikal, ug uban pang kontaminasyon.",
            "Gamit og limpyo nga gamit sa paghakot, pagpauga, ug storage.",
            f"Itago ang {crop} nga bulag sa abono, pestisidyo, treated pallets, o uban pang posibleng kontaminasyon.",
            "Limpyohi ang storage sa dili pa gamiton, labi na kung naay duda sa pestisidyo.",
        ], [
            PlanAction(task="Andama ang limpyo nga patuyuan ug storage.", observe="Hugaw, tagas, peste, sudlanan sa kemikal, o treated pallets.", ask_for_help_if="Posibleng naay pestisidyo o kontaminasyon ang storage."),
            PlanAction(task=f"Hawiri ang naani nga {crop} gamit ang limpyo nga materyales.", observe="Direktang dikit sa yuta o nasagol sa kontaminant.", ask_for_help_if="Walay limpyo nga patuyuan o panghakot."),
        ]

    if key == "records":
        return "Mga Record nga Tipigan", [
            "Isulat ang petsa sa pagtanom, gigikanan sa binhi, resulta sa soil test, nutrient material, paggamit sa pestisidyo o chemical, obserbasyon sa peste, problema sa panahon, ug resulta sa ani.",
            "Para sa abono o organic soil amendment, isulat ang gigikanan, pag-andam, petsa, gidaghanon, paagi, ug responsable.",
            "Para sa pestisidyo o agricultural chemical, isulat ang pagpalit, paggamit, storage, disposal, pagsunod sa label, ug pre-harvest interval.",
        ], [
            PlanAction(task="Isulat ang record sa mismong adlaw sa trabaho.", observe="Nawalang petsa, materyal, o obserbasyon.", ask_for_help_if="Dili nimo mailhan unsang input ang gigamit."),
        ]

    return "Mga Pahimangno ug Pagpangayo og Tabang", _warnings_ceb(request), [
        PlanAction(task="I-report dayon ang seryoso o dili klaro nga problema.", observe="Paspas mokalat nga peste o sakit, posibleng kontaminasyon, baha, kauga, o dili klaro nga paggamit sa pestisidyo.", ask_for_help_if="Naay bisan unsang warning condition."),
    ]


def _timeline_ceb(request: FarmingPlanRequest, timeline: list[TimelineItem]) -> list[TimelineItem]:
    if request.planning_mode == "already_planted":
        return [
            TimelineItem(
                period="Kasamtangang semana",
                approximate_date=f"Kasamtangang yugto: {request.current_stage}",
                task="Sugdi sa pag-check sa uma ug pagsulat og record.",
                how_to_steps=[
                    "Lakawa ang kilid ug tunga nga parte sa uma.",
                    "Isulat ang tubig, sagbot, pagpanilaw, kadaot sa dahon, spots sa sakit, ug dili patas nga tubo.",
                    "Isulat ang kasamtangang yugto ug problema sa record template.",
                ],
                observe="Tubig, sagbot, timailhan sa peste, pagpanilaw, spots sa sakit, pagdapa, ug mokalat nga kadaot.",
                ask_for_help_if="Mokalat ang kadaot, dili makontrol ang tubig, o dili klaro ang yugto sa tanom.",
            )
        ]
    return [
        TimelineItem(
            period=_period_ceb(item.period),
            approximate_date=_date_text_ceb(item.approximate_date),
            task=_timeline_task_ceb(_period_ceb(item.period)),
            how_to_steps=_timeline_steps_ceb(_period_ceb(item.period), request),
            observe=_timeline_observe_ceb(_period_ceb(item.period)),
            ask_for_help_if=_timeline_help_ceb(_period_ceb(item.period)),
        )
        for item in timeline
    ]


def _timeline_task_ceb(period: str) -> str:
    return {
        "4-6 ka semana sa dili pa magtanom": "Bisitaha ang MAO ug ikumpirma ang lokal nga plano sa pagtanom.",
        "3-4 ka semana sa dili pa magtanom": "Kuhaa ang soil sample ug susiha ang kontrol sa tubig.",
        "1-2 ka semana sa dili pa magtanom": "Andama ang binhi, punlaan, gamit, agianan sa uma, ug trabahante.",
        "Semana sa pagtanom": "Magtanom lang kung andam ang kondisyon sa uma.",
        "Kada semana human magtanom": "Mag-scout sa uma kada semana.",
        "Sa dili pa anihon": "Andama ang limpyo nga patuyuan ug storage.",
    }.get(period, "Sunda ang nakatakdang trabaho ug magsulat og record.")


def _timeline_steps_ceb(period: str, request: FarmingPlanRequest) -> list[str]:
    crop = _crop_ceb(request.crop)
    if period == "4-6 ka semana sa dili pa magtanom":
        return [
            "Dad-a sa MAO ang lokasyon, target nga petsa sa pagtanom, tinubdan sa tubig, ug tala sa uma.",
            "Pangutana kung ang timing angay sa lokal nga cropping calendar ug kondisyon sa tubig.",
            f"Ikumpirma ang rekomendadong variety sa {crop} ug asa magpa-soil test.",
        ]
    if period == "3-4 ka semana sa dili pa magtanom":
        return [
            "Lakaw og zigzag sa uma ug kuha og gagmay nga sample sa yuta sa daghang normal nga parte.",
            "Likayi ang lahi nga spots sama sa compost pile, nasunog nga lugar, kanal, o kilid sa uma.",
            "Sagola ang yuta sa limpyo nga sudlanan ug dad-a sa MAO o laboratoryo.",
            "Susiha ang pilapil, kanal, ug drainage samtang naghuwat sa giya.",
        ]
    if period == "1-2 ka semana sa dili pa magtanom":
        return [
            "Andama ang limpyo nga binhi o seedling gikan sa kasaligang gigikanan.",
            "Andama ang punlaan o uma ug siguroa nga andam ang gamit ug trabahante.",
            "Ayuhon ang agianan, pilapil, kanal, ug drainage sa dili pa adlaw sa pagtanom.",
        ]
    if period == "Semana sa pagtanom":
        return [
            "Gamita ang rekomendasyon sa MAO o teknisyan sa paagi sa pagtanom, distansya, ug gidaghanon sa binhi o seedling.",
            "Magtanom sa patas nga uma nga naay angay nga kaumog ug klaro nga linya para sayon ma-check.",
            "Kung uga ang yuta, patubigi o hulata ang ulan; kung baha, paagasa una.",
            "Isulat ang petsa sa pagtanom, gigikanan sa binhi, paagi, kaumog sa yuta, ug uga o baha nga parte.",
        ]
    if period == "Kada semana human magtanom":
        return [
            "Lakawa ang uma kausa kada semana, apil ang kilid ug tunga.",
            "Susiha ang tubig, sagbot, pagpanilaw, buslot o kadaot sa dahon, suso, insekto, spots sa sakit, huyang nga tubo, ug pagdapa.",
            "Kuhaa og litrato ang lahi nga sintomas ug tan-awa kung mokalat ba ang kadaot.",
        ]
    return [
        "Limpyohi ang patuyuan, sako, gamit sa paghakot, ug storage.",
        f"Ilayo ang {_stored_crop_ceb(request.crop)} sa yuta, hayop, abono, pestisidyo, hugaw nga gamit, ug treated pallets.",
        "Susiha ang pesticide record para sa pre-harvest interval sa dili pa anihon.",
    ]


def _timeline_observe_ceb(period: str) -> str:
    if period == "4-6 ka semana sa dili pa magtanom":
        return "Lokal nga cropping calendar, kasiguruhan sa tubig, variety advice, ug soil test options."
    if period == "3-4 ka semana sa dili pa magtanom":
        return "Kahimtang sa soil sample, barado nga kanal, guba nga pilapil, liki sa uga nga yuta, o baha."
    if period == "1-2 ka semana sa dili pa magtanom":
        return "Kondisyon sa binhi, kahandaan sa punlaan, gamit, pagpatag sa uma, ug kontrol sa tubig."
    if period == "Semana sa pagtanom":
        return "Aktuwal nga distansya o seeding rate, kaumog sa yuta, patas nga linya, drainage, ug kondisyon sa binhi o seedling."
    if period == "Kada semana human magtanom":
        return "Tubig, sagbot, pagpanilaw, kadaot sa dahon, suso, insekto, spots sa sakit, dili patas nga tubo, pagdapa, ug mokalat nga kadaot."
    return "Limpyo nga patuyuan, limpyo nga storage, timailhan sa peste, sudlanan sa kemikal, hugaw nga sako, o treated pallets."


def _timeline_help_ceb(period: str) -> str:
    if period == "4-6 ka semana sa dili pa magtanom":
        return "Dili angay ang target nga petsa sa lokal nga tubig o cropping conditions."
    if period == "3-4 ka semana sa dili pa magtanom":
        return "Dili makakuha og soil testing guidance o dili makapundo/makapaagas og tubig ang uma."
    if period == "1-2 ka semana sa dili pa magtanom":
        return "Dili sigurado ang kalidad sa binhi o dili mahuman ang pag-andam sa uma."
    if period == "Semana sa pagtanom":
        return "Dili klaro ang distansya o seeding rate, dili sigurado ang binhi, o uga, baha, dili patas, o dili moagas ang uma."
    if period == "Kada semana human magtanom":
        return "Dili mailhan ang peste, mokalat ang kadaot, mograbe ang pagpanilaw, o naay water stress."
    return "Posibleng kontaminado ang patuyuan o storage, o dili klaro ang waiting time sa pestisidyo."


def _glossary_ceb() -> list[GlossaryItem]:
    return [
        GlossaryItem(term="Pilapil", explanation="Gipataas nga yuta palibot sa uma nga makatabang mopundo o mogiya sa tubig."),
        GlossaryItem(term="Punlaan", explanation="Gamay nga giandam nga lugar diin patubuon ang seedling sa dili pa ibalhin."),
        GlossaryItem(term="IPM", explanation="Pagdumala sa peste nga magsugod sa pag-check ug paglikay, dili dayon pag-spray."),
        GlossaryItem(term="Pre-harvest interval", explanation="Kinahanglan nga hulaton human mogamit og pestisidyo sa dili pa anihon."),
        GlossaryItem(term="Soil amendment", explanation="Materyal nga idugang aron mapaayo ang yuta, kung angay ug girekomenda."),
    ]


def _decision_rows_ceb(request: FarmingPlanRequest) -> list[DecisionRow]:
    crop = _crop_ceb(request.crop)
    rows = [
        DecisionRow(situation="Uga kaayo ang uma sa dili pa magtanom", first_check="Susiha ang tinubdan sa tubig ug duol nga mga uma.", what_to_do_next="Ayaw ipadayon ang final land preparation hangtod realistic ang tubig.", contact_mao_if="Dili sigurado ang tubig o nagpadayon ang kauga."),
        DecisionRow(situation="Baha ang uma ug dili moagas", first_check="Susiha ang drainage, kanal, ug guba nga pilapil.", what_to_do_next="Limpyohi ang drainage kung luwas ug ipalangan ang punlaan o pagtanom.", contact_mao_if="Dili mahubas ang tubig o lubog ang seedling."),
        DecisionRow(situation="Nagpanilaw ang dahon", first_check="Susiha ang tubig ug kung mokalat ang pagpanilaw.", what_to_do_next="Isulat ang sintomas ug pangayo og soil o plant-based guidance sa dili pa magbutang og sustansiya.", contact_mao_if="Mokalat ang pagpanilaw, huyang ang tubo, o walay soil test."),
        DecisionRow(situation="Naay insekto, suso, o kadaot sa dahon", first_check="Ilha ang peste ug tan-awa kung mokalat ang kadaot.", what_to_do_next="Ayaw dayon pag-spray; kuha og litrato ug obserbahi ang kadako sa kadaot.", contact_mao_if="Dili mailhan ang peste o mokalat ang kadaot."),
        DecisionRow(situation="Nagdaghan ang sagbot", first_check=f"Susiha kung nakigkompetensya ang sagbot sa batan-ong {crop}.", what_to_do_next="Lihok og sayo gamit ang lokal nga giya sa weed management ug magsulat og record.", contact_mao_if=f"Dili ka sigurado kung sagbot ang tanom o napugngan ang tubo sa {crop}."),
        DecisionRow(situation="Hugaw ang anihan o storage", first_check="Tan-awa ang yuta, peste, hayop, sudlanan sa kemikal, hugaw nga gamit, o treated pallets.", what_to_do_next="Limpyohi o pagpili og laing patuyuan ug storage sa dili pa anihon.", contact_mao_if="Naay duda sa pestisidyo o kontaminasyon."),
    ]
    if request.water_source in {"rainfed", "unknown"}:
        rows.insert(0, DecisionRow(situation="Dili sigurado ang ulan sa dili pa magtanom", first_check="Pangutana sa duol nga mag-uuma ug MAO bahin sa lokal nga timing sa ulan.", what_to_do_next="Ipalangan ang lisod-usbon nga trabaho hangtod realistic ang kaumog sa pagtanom.", contact_mao_if="Walay kasaligang tubig para sa planong semana."))
    return rows


def _material_checklist_ceb(request: FarmingPlanRequest) -> list[MaterialChecklistGroup]:
    crop = _crop_ceb(request.crop)
    return [
        MaterialChecklistGroup(category="Binhi", items=[f"Rekomendadong variety sa {crop}", "Limpyo nga gigikanan sa binhi", "Sudlanan sa binhi o seedling"]),
        MaterialChecklistGroup(category="Gamit sa uma", items=["Araro o hand tractor access", "Gamit sa pagpatag", "Bota", "Marker sa uma"]),
        MaterialChecklistGroup(category="Kontrol sa tubig", items=["Gamit sa paglimpyo sa kanal", "Materyales sa pag-ayo sa pilapil", "Agianan sa drainage"]),
        MaterialChecklistGroup(category="Records", items=["Notebook", "Bolpen", "Phone camera para sa litrato sa uma"]),
        MaterialChecklistGroup(category="Kaluwasan", items=["Guwantes", "Mask o PPE kung mohikap og kemikal", "Label ug storage area para sa inputs"]),
        MaterialChecklistGroup(category="Human sa ani", items=["Limpyo nga sako", "Limpyo nga drying mat", "Limpyo nga storage", "Limpyo nga panghakot"]),
    ]


def _record_templates_ceb() -> list[RecordTemplate]:
    return [
        RecordTemplate(title="Record sa Trabaho sa Uma", columns=["Petsa", "Trabaho", "Kondisyon sa uma", "Input nga gigamit", "Gidaghanon", "Obserbasyon", "Responsable"], sample_row=["Hunyo 15", "Pagtanom", "Basa ug patas", "Binhi", "Isulat ang aktuwal nga gidaghanon", "Maayo o dili patas", "Ngalan"]),
        RecordTemplate(title="Record sa Pestisidyo o Agricultural Chemical", columns=["Petsa", "Peste/problema", "Produkto nga gigamit", "Nasunod ang label?", "Nagamit ang PPE?", "Pre-harvest interval", "Kinsa ang naggiya?"], sample_row=["Isulat ang petsa", "Dili mailhan nga insekto", "Wala hangtod naay giya", "Oo/Dili", "Oo/Dili", "Isulat ang naa sa label", "MAO o teknisyan"]),
        RecordTemplate(title="Kada Semana nga Obserbasyon sa Uma", columns=["Petsa", "Kondisyon sa tubig", "Sagbot", "Timailhan sa peste", "Pagpanilaw/spots", "Naa bay litrato?", "Sunod nga aksyon"], sample_row=["Isulat ang petsa", "Uga/basa/baha", "Gamay/medium/daghan", "Ihulagway ang timailhan", "Ihulagway ang sintomas", "Oo/Dili", "Bantayi o pangutana sa MAO"]),
    ]


def _mao_questions_ceb(request: FarmingPlanRequest) -> list[MaoQuestion]:
    crop = _crop_ceb(request.crop)
    questions = [
        MaoQuestion(topic="Petsa sa pagtanom ug tubig", question=f"Angay ba ang pagtanom palibot sa {request.target_planting_date} sa lokal nga kalendaryo sa {crop}, ulan, irigasyon, ug drainage para sa {request.location_label}?"),
        MaoQuestion(topic="Soil testing", question="Asa nako dad-on ang gisagol nga soil sample, ug kinsa ang motabang pagsabot sa resulta para sa abono o amendment schedule?"),
        MaoQuestion(topic="Binhi o variety", question=f"Unsang variety sa {crop} ug limpyo nga seed source ang rekomendado para sa kondisyon sa uma ug tubig?"),
    ]
    if {"pests", "weeds", "poor_growth"} & set(request.concerns):
        questions.append(MaoQuestion(topic="Kontak para sa problema sa uma", question="Kung makakita ko og insekto, suso, sagbot, buslot sa dahon, pagpanilaw, o spots sa sakit, kinsa ang motabang moila sa problema sa dili pa mogamit og pestisidyo o sustansiya?"))
    if "harvest_post_harvest" in request.concerns:
        questions.append(MaoQuestion(topic="Human sa ani", question="Unsang lokal nga paagi sa pagpauga ug storage ang sundon aron malikayan ang kontaminasyon?"))
    return questions


def _warnings_ceb(request: FarmingPlanRequest) -> list[str]:
    warnings = [
        "Kini nga plano giya sa desisyon. Dili kini motagna sa ani ug dili mopuli sa tambag sa lokal nga teknisyan.",
    ]
    if "pests" in request.concerns:
        warnings.append("Kung dili mailhan ang peste o mokalat ang kadaot, konsultaha ang MAO sa dili pa mogamit og pestisidyo.")
    if "fertilizer_nutrient" in request.concerns or "poor_growth" in request.concerns:
        warnings.append("Ayaw tagnaa ang gidaghanon sa sustansiya. Gamit og soil o plant-based analysis ug giya sa lokal nga teknisyan.")
    if request.soil_condition == "flooded" or "heavy_rain_flooding" in request.concerns:
        warnings.append(f"Ang baha dali makadaot sa {_crop_ceb(request.crop)}. Pangayo og lokal nga tabang kung dili mahubas ang tubig o lubog ang tanom.")
    if request.soil_condition == "dry" or "water_shortage" in request.concerns:
        warnings.append("Kinahanglan og lokal nga plano sa tubig kung uga ang uma sa dili pa mohimo og lisod-usbon nga trabaho.")
    return warnings


def _fallback_ceb(value: str | None) -> str | None:
    if not value:
        return value
    if "Unsupported crop" in value:
        return "Dili suportado ang tanom sa Phase 1."
    return "Kulang ang nakit-an nga source-backed evidence; ikumpirma sa MAO."


def _planning_basis_ceb(request: FarmingPlanRequest) -> str:
    if request.planning_mode == "planning_to_plant":
        return f"nagplano nga magtanom; target nga petsa: {request.target_planting_date}"
    return f"nakatanom na; kasamtangang yugto: {request.current_stage}"


def _period_ceb(value: str) -> str:
    return {
        "4-6 weeks before planting": "4-6 ka semana sa dili pa magtanom",
        "3-4 weeks before planting": "3-4 ka semana sa dili pa magtanom",
        "1-2 weeks before planting": "1-2 ka semana sa dili pa magtanom",
        "Planting week": "Semana sa pagtanom",
        "Weekly after planting": "Kada semana human magtanom",
        "Before harvest": "Sa dili pa anihon",
    }.get(value, value)


def _date_text_ceb(value: str) -> str:
    replacements = {
        "Relative to target planting date": "Base sa target nga petsa sa pagtanom",
        "Target week": "Target nga semana",
        "From planting until harvest": "Gikan pagtanom hangtod ani",
        "Several weeks before expected harvest": "Pipila ka semana sa dili pa gipaabot nga ani",
        "January": "Enero",
        "February": "Pebrero",
        "March": "Marso",
        "April": "Abril",
        "May": "Mayo",
        "June": "Hunyo",
        "July": "Hulyo",
        "August": "Agosto",
        "September": "Setyembre",
        "October": "Oktubre",
        "November": "Nobyembre",
        "December": "Disyembre",
    }
    text = value
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _concern_summary_ceb(concerns: list[str]) -> str:
    return ", ".join(_concern_label_ceb(concern) for concern in concerns)


def _concern_label_ceb(concern: str) -> str:
    return {
        "pests": "peste",
        "weeds": "sagbot",
        "poor_growth": "huyang nga tubo",
        "fertilizer_nutrient": "kabalaka sa abono o sustansiya",
        "water_shortage": "kakulang sa tubig",
        "heavy_rain_flooding": "kusog nga ulan o baha",
        "harvest_post_harvest": "ani o human sa ani",
        "none": "walay urgent nga kabalaka",
    }.get(concern, concern.replace("_", " "))


def _concern_guidance_ceb(request: FarmingPlanRequest, concern: str) -> list[str]:
    crop = _crop_ceb(request.crop)
    if concern == "pests":
        return [
            "Para sa peste: ilha una ang peste, tan-awa kung mokalat ang kadaot, ug kuha og klaro nga litrato sa apektadong dahon, punoan, o tanom.",
            "Ayaw dayon pag-spray o pagpili og pestisidyo gikan sa app; pangutana sa MAO o kwalipikadong applicator kung dili klaro ang peste o paggamit sa pestisidyo.",
        ]
    if concern == "weeds":
        return [
            f"Para sa sagbot: tan-awa kung nakigkompetensya ang sagbot sa batan-ong {crop}, labi na sa kilid, basang parte, ug nipis ang tubo.",
            "Lihok og sayo gamit ang lokal nga giya sa weed management ug isulat ang paagi nga gigamit.",
        ]
    if concern == "poor_growth":
        return [
            "Para sa huyang nga tubo: itandi ang huyang ug himsog nga parte, dayon susiha ang tubig, pagkapatas sa tubo, pagpanilaw, peste, ug spots sa sakit.",
            "Ayaw tagnaa ang hinungdan o magbutang og sustansiya isip trial; dad-a ang tala o litrato sa MAO kung magpadayon ang huyang nga tubo.",
        ]
    if concern == "fertilizer_nutrient":
        return [
            "Para sa kabalaka sa abono o sustansiya: gamit og soil o plant-based analysis sa dili pa magdesisyon sa materyal, timing, o gidaghanon.",
            "Isulat ang daang paggamit sa abono o amendment, tubag sa tanom, ug bisan unsang pagpanilaw o dili patas nga tubo sa dili pa mangayo og lokal nga giya.",
        ]
    if concern == "water_shortage":
        return [
            "Para sa kakulang sa tubig: susiha ang tinubdan sa tubig, kanal, pilapil, duol nga uma, ug kung uga kaayo ang yuta para sa sunod nga trabaho.",
            "Ipalangan ang lisod-usbon nga trabaho kung dili realistic ang tubig.",
        ]
    if concern == "heavy_rain_flooding":
        return [
            "Para sa kusog nga ulan o baha: susiha ang drainage, kanal, guba nga pilapil, ug kung lubog ang seedling o tanom.",
            "Pangayo dayon og lokal nga tabang kung dili mahubas ang tubig o nagpabiling lubog ang tanom.",
        ]
    if concern == "harvest_post_harvest":
        return [
            f"Para sa ani o human sa ani: ilayo ang {_stored_crop_ceb(request.crop)} sa yuta, hugaw nga gamit, hayop, sudlanan sa kemikal, ug treated pallets.",
            "Andama ang limpyo nga patuyuan, panghakot, ug storage sa dili pa magsugod ang ani.",
        ]
    return [
        "Walay urgent nga kabalaka nga gipili. Gamita ang kada semana nga checklist sa tubig, sagbot, peste, pagpanilaw, spots sa sakit, ug dili patas nga tubo.",
    ]


def _concern_action_ceb(request: FarmingPlanRequest, concern: str) -> PlanAction:
    crop = _crop_ceb(request.crop)
    if concern == "pests":
        return PlanAction(task="Tubaga karon ang kabalaka sa peste.", observe="Pag-ila sa peste, gidaghanon sa apektadong tanom, litrato, ug kung mokalat ang kadaot.", ask_for_help_if="Dili mailhan ang peste, mokalat ang kadaot, o gihunahuna ang pestisidyo.")
    if concern == "weeds":
        return PlanAction(task="I-map ang sagbot sa uma.", observe=f"Klase sa sagbot, kadaghanon, pagpugong sa batan-ong {crop}, ug basa o nipis ang tubo nga parte.", ask_for_help_if=f"Dili ka sigurado kung sagbot ang tanom o napugngan ang tubo sa {crop}.")
    if concern == "poor_growth":
        return PlanAction(task="Itandi ang huyang ug himsog nga parte sa tanom.", observe="Tubig, pagpanilaw, peste, spots sa sakit, gaps sa tanom, ug bag-ong trabaho sa uma.", ask_for_help_if="Mokalat ang huyang nga tubo, mograbe ang pagpanilaw, o walay soil o plant analysis.")
    if concern == "fertilizer_nutrient":
        return PlanAction(task="Andam para sa soil o plant-based nutrient guidance.", observe="Status sa soil test, daang nutrient use, pagpanilaw, dili patas nga tubo, ug tubag sa tanom.", ask_for_help_if="Nagkinahanglan og nutrient advice pero walay soil test o plant-based analysis.")
    if concern == "water_shortage":
        return PlanAction(task="Susiha kung igo ang tubig sa dili pa sunod nga trabaho.", observe="Kasiguruhan sa tubig, agos sa kanal, liki sa uga nga yuta, kondisyon sa duol nga uma, ug kaumog sa yuta.", ask_for_help_if="Walay kasaligang tubig o nagpadayon ang kauga.")
    if concern == "heavy_rain_flooding":
        return PlanAction(task="Susiha ang drainage ug lubog nga parte sa tanom.", observe="Barado nga drainage, guba nga pilapil, giladmon sa tubig, lubog nga seedling, ug nagtindog nga tubig.", ask_for_help_if="Dili mahubas ang tubig o nagpabiling lubog ang tanom.")
    if concern == "harvest_post_harvest":
        return PlanAction(task="Susiha ang anihan, patuyuan, ug storage.", observe="Dikit sa yuta, peste, tagas, hugaw nga sako, sudlanan sa kemikal, o treated pallets.", ask_for_help_if="Walay limpyo nga patuyuan o storage, o naay duda sa kontaminasyon.")
    return PlanAction(task="Gamita ang kada semana nga field check.", observe="Tubig, sagbot, peste, pagpanilaw, spots sa sakit, dili patas nga tubo, ug records sa uma.", ask_for_help_if="Naay motungha, mograbe, o dili klaro nga problema.")


def _safe_user_text_ceb(value: str) -> str:
    text = " ".join(value.split())
    for term in ("capital", "budget", "cost", "price"):
        text = text.replace(term, "[gitangtang nga money term]")
        text = text.replace(term.title(), "[gitangtang nga money term]")
        text = text.replace(term.upper(), "[gitangtang nga money term]")
    return text


def _crop_ceb(crop: str) -> str:
    return {"rice": "humay", "corn": "mais"}.get(crop, crop)


def _stored_crop_ceb(crop: str) -> str:
    if crop == "corn":
        return "naaning mais, bunga sa mais, o lugas sa mais"
    return "humay"


def _farming_type_ceb(value: str) -> str:
    return {
        "conventional": "conventional",
        "organic_traditional": "organiko/tradisyonal",
        "unknown": "wala pa masiguro",
    }.get(value, value)


def _crop_fil(crop: str) -> str:
    return {"rice": "palay", "corn": "mais"}.get(crop, crop)


def _stored_crop_fil(crop: str) -> str:
    if crop == "corn":
        return "inaning mais, busal ng mais, o butil ng mais"
    return "palay"


def _farming_type_fil(value: str) -> str:
    return {
        "conventional": "karaniwang",
        "organic_traditional": "organiko/tradisyonal",
        "unknown": "hindi pa tiyak",
    }.get(value, value)


def _is_surigao_area(request: FarmingPlanRequest) -> bool:
    text = f"{request.barangay} {request.municipality} {request.province}".lower()
    return "surigao" in text or "marga" in text

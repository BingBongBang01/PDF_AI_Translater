import os
import re

with open('translate_pdf.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add Pipeline imports
if 'from pdf_engine.pipeline import' not in content:
    content = content.replace('from pdf_engine.preprocess.extractor import', 'from pdf_engine.pipeline import TranslationPipeline, PipelineState\nfrom pdf_engine.preprocess.extractor import')

# Find the start block
start_str = '''    # [1] 추출
    page_filter = parse_pages(args.pages, doc.page_count)'''

# Replace up to dry_run
new_start_str = '''    # [1] Pipeline Setup
    page_filter = parse_pages(args.pages, doc.page_count)
    args.page_filter = page_filter'''
content = content.replace(start_str, new_start_str)

# Find the execution block
trans_block_start = '''    # [2]+[3] 번역
    aborted = False
    if n_target == 0:
        pass  # 위에서 이미 안내함 - API 키 확인/배치 구성 등 번역 단계 전체를 건너뜀
    elif args.import_json:
        import_translations(args.import_json, segments)
    elif args.mock:
        print("[2/4] 배치: (mock 모드 — API 호출 생략)")
        mock_translate(segments)
        print("[3/4] 모의 번역 완료")
    else:
        batches = list(make_batches([s for s in segments if s.needs_translation],
                                    args.batch_chars, args.batch_segs))
        pool = get_key_pool(args)
        # 로컬 NPU/GPU 폴백: --local-device로 지정한 장치들을 풀 맨 뒤(최후 순위)에 추가.
        # 여러 장치를 지정하면 먼저 적은 장치부터 순서대로 시도한다(예: "npu,gpu" -> NPU 우선,
        # NPU 쪽 키가 전부 죽어야 GPU로 넘어감 - next_alive_index가 pool 등장 순서를 따름).
        requested_devices = _parse_local_devices(args)
        if requested_devices:
            runtime = args.local_runtime
            spec = get_runtime_spec(runtime)
            added = []
            for device in requested_devices:
                supports_key = f"supports_{device}"
                if not spec.get(supports_key, False):
                    print(f"[정보] {spec['label']}는 {device.upper()}를 지원하지 않아 건너뜀 "
                          f"(--local-runtime {runtime} --local-device {device})")
                    continue
                entry = make_local_entry(args, device=device)
                pool.append(entry)
                added.append(entry.label)
            if added:
                print(f"[정보] 로컬 폴백 활성화: {', '.join(added)} "
                      f"(모델 {args.model_local or DEFAULT_MODELS['local']}, "
                      f"포트 {args.local_port}, 클라우드 전부 소진 시에만 사용)")
        print(f"[2/4] 배치: {len(batches)}개 (배치당 최대 {args.batch_chars}자 / "
              f"{args.batch_segs}세그먼트)")
        system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        system_prompt_local = SYSTEM_PROMPT_LOCAL_PATH.read_text(encoding="utf-8") \\
            if SYSTEM_PROMPT_LOCAL_PATH.exists() else None
        template = USER_TEMPLATE_PATH.read_text(encoding="utf-8")
        glossary_text = load_glossary(args.glossary)
        try:
            aborted = translate_all_batches(pool, args, system_prompt, template,
                                            segments, glossary_text,
                                            system_prompt_local=system_prompt_local)
        finally:
            shutdown_local_runtime()'''

new_trans_block = '''    # [2]+[3] 번역 Pipeline
    aborted = False
    if n_target == 0:
        pass
    elif args.import_json:
        import_translations(args.import_json, segments)
    elif args.mock:
        print("[2/4] 배치: (mock 모드 — API 호출 생략)")
        mock_translate(segments)
        print("[3/4] 모의 번역 완료")
    else:
        pool = get_key_pool(args)
        requested_devices = _parse_local_devices(args)
        if requested_devices:
            runtime = args.local_runtime
            spec = get_runtime_spec(runtime)
            for device in requested_devices:
                if spec.get(f"supports_{device}", False):
                    pool.append(make_local_entry(args, device=device))
        
        system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        system_prompt_local = SYSTEM_PROMPT_LOCAL_PATH.read_text(encoding="utf-8") if SYSTEM_PROMPT_LOCAL_PATH.exists() else None
        template = USER_TEMPLATE_PATH.read_text(encoding="utf-8")
        glossary_text = load_glossary(args.glossary)
        
        pipeline = TranslationPipeline(
            args=args, system_prompt=system_prompt, template=template,
            glossary_text=glossary_text, pool=pool, system_prompt_local=system_prompt_local
        )
        state = PipelineState(doc, args)
        state.segments = segments
        
        try:
            state = pipeline.run_translation_phase(state)
            segments = state.segments
        finally:
            shutdown_local_runtime()'''

content = content.replace(trans_block_start, new_trans_block)


# Now replace the rebuild_pdf section
rebuild_block_start = '''    work_doc = None
    try:
        work_doc = pymupdf.open(tmp_path)
        if work_doc.needs_pass:
            raise RuntimeError("임시 출력 PDF가 암호화되어 있습니다")

        truncated = rebuild_pdf(work_doc, segments, args.font_scale)
        try:
            # 전체 문서 폰트 재구성은 하지 않는다. subset_fonts()가 비대상 페이지의
            # 객체까지 순회할 수 있으므로 부분 번역 모드에서는 오히려 위험하다.
            pass
        except Exception:
            pass

        # 원본 복사본에 변경 객체만 추가 기록. 지정 범위 밖 페이지는 그대로 유지.
        if work_doc.can_save_incrementally():
            work_doc.saveIncr()
            work_doc.close()
            work_doc = None
        else:
            # MuPDF가 원본을 repair하여 증분 저장이 불가능한 경우의 안전 폴백.
            # PDF 페이지를 이미지/텍스트로 재렌더링하지 않는다. 수정 페이지만 별도 PDF로
            # 내보낸 뒤 pypdf가 원본 페이지 객체를 복제하고 해당 페이지만 교체한다.
            # 따라서 비대상 페이지의 글꼴/좌표/콘텐츠 스트림은 재조판되지 않는다.
            patch_path = tmp_path.with_name(tmp_path.stem + ".patch.pdf")
            patched_pages = sorted(current_target_pages)
            patch_doc = pymupdf.open()
            for page_no in patched_pages:
                patch_doc.insert_pdf(work_doc, from_page=page_no - 1, to_page=page_no - 1)
            patch_doc.save(patch_path, garbage=0, deflate=False)
            patch_doc.close()
            work_doc.close()
            work_doc = None

            try:
                from pypdf import PdfReader, PdfWriter
            except ImportError as ie:
                raise RuntimeError(
                    "증분 저장 불가 PDF 폴백에 pypdf가 필요합니다. "
                    "먼저 'pip install pypdf'를 실행하세요."
                ) from ie

            src_reader = PdfReader(str(in_path), strict=False)
            patch_reader = PdfReader(str(patch_path), strict=False)
            writer = PdfWriter()
            patch_map = {pno: i for i, pno in enumerate(patched_pages)}
            for pno in range(1, len(src_reader.pages) + 1):
                if pno in patch_map:
                    writer.add_page(patch_reader.pages[patch_map[pno]])
                else:
                    writer.add_page(src_reader.pages[pno - 1])
            with open(tmp_path, "wb") as fp:
                writer.write(fp)
            try:
                patch_path.unlink()
            except Exception:
                pass
            print(f"[저장] 증분 저장 불가 -> pypdf 페이지 객체 교체 폴백 사용 ({len(patched_pages)}페이지 수정)")

    finally:
        if work_doc is not None:
            work_doc.close()'''

new_rebuild_block = '''    # [4] Output Pipeline Rebuild
    if 'pipeline' in locals():
        state.tmp_path = tmp_path
        state.current_target_pages = current_target_pages
        pipeline.run_output_phase(state)
    else:
        # Fallback if pipeline skipped (mock, json, empty)
        pass'''

content = content.replace(rebuild_block_start, new_rebuild_block)

with open('translate_pdf.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patched translate_pdf.py successfully')

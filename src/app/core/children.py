# 실험 노트북(07·19·21·22)의 채택 코드를 글자 그대로 옮긴 파일. 노트북과 같은 결과가 나오도록 직접 고치지 않는다.
CHILD_HEAD = r"""import csv, json, os, sys, time
T_START = time.perf_counter()
import numpy as np
import torch
from PIL import Image

a = json.loads(sys.stdin.read())
IMPORT_SEC = round(time.perf_counter() - T_START, 2)
FIELDS = ['file', 'sec', 'extra_sec', 'peak_vram_gb', 'error', 'info']
STAGE = dict(peak=0.0)


def log(msg):
    m, s = divmod(int(time.perf_counter() - T_START), 60)
    vr = f'VRAM {torch.cuda.memory_allocated() / 1024**3:.1f}GB (최대 {torch.cuda.max_memory_allocated() / 1024**3:.1f}GB)'
    print(f'[{time.strftime("%H:%M:%S")} | 경과 {m // 60:d}:{m % 60:02d}:{s:02d} | {vr}] {msg}', flush=True)


def peak_now():
    p = torch.cuda.max_memory_allocated() / 1024**3
    STAGE['peak'] = max(STAGE['peak'], p)
    return round(p, 2)


def write(rec):
    new = not os.path.exists(a['csv'])
    with open(a['csv'], 'a', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: rec.get(k, '') for k in FIELDS})


def write_stage(load_sec, extra_load_sec=0.0):
    json.dump(dict(import_sec=IMPORT_SEC, load_sec=load_sec, extra_load_sec=round(extra_load_sec, 2),
                   peak_vram_gb=round(STAGE['peak'], 2)), open(a['stage_json'], 'w', encoding='utf-8'))
"""

CHILD_COPY = r"""from transformers import AutoModelForImageTextToText, AutoProcessor

exec(a['validator'])
log('Qwen 로드 시작')
t_load = time.perf_counter()
proc = AutoProcessor.from_pretrained(a['repo'])
model = AutoModelForImageTextToText.from_pretrained(a['repo'], dtype=torch.bfloat16, device_map='cuda').eval()
load_sec = round(time.perf_counter() - t_load, 2)
peak_now()
gc = model.generation_config
GEN_CFG = dict(temperature=gc.temperature, top_p=gc.top_p, top_k=gc.top_k, repetition_penalty=getattr(gc, 'repetition_penalty', None))
log(f'Qwen 로드 끝 {load_sec}초 | sampling defaults {GEN_CFG}')


def gen(messages, sample, n=1):
    inputs = proc.apply_chat_template(messages, add_generation_prompt=True, tokenize=True, return_dict=True,
                                      return_tensors='pt').to(model.device)
    kw = dict(do_sample=True, num_return_sequences=n) if sample else dict(do_sample=False)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=a['max_new_tokens'], **kw)
    n_in = inputs['input_ids'].shape[1]
    return proc.batch_decode(out[:, n_in:], skip_special_tokens=True, clean_up_tokenization_spaces=False)


def probs_of(text, t):
    if t['kind'] == 'b':
        return check_b(text, t['request'], a['banned_promo'])
    if t['kind'] == 'c':
        return check_c(text)
    if t['section'] == 'intro':
        return check(text, t['must'], t['allowed'], a['banned_promo'], a['banned_cliche'], t['need_must'])
    return check_section(text, t['key'], t['n_sent'], t['max_chars'], t['json_fmt'], t['allowed'], a['banned_promo'],
                         a['banned_cliche'], t.get('polite', False))


def with_ro(must):
    # ③④처럼 꼭 넣을 문구가 없는 섹션의 재요청(존댓말)에서도 쓰므로 빈 문구 허용
    c = must[-1:]
    if '가' <= c <= '힣' and (ord(c) - 0xAC00) % 28 not in (0, 8):
        return must + '으로'
    return must + '로'


def feedback(probs, must):
    # 실패 이유 줄 아래에, 해당하는 고치는 방법 줄을 붙임
    out = []
    for p in probs:
        out.append('- ' + p)
        for key, mark in a['fb_keys'].items():
            if mark in p and key in a['fb_hints']:
                out.append(a['fb_hints'][key].format(must=must, must_ro=with_ro(must), eul=_josa(must, '을', '를')))
    return a['fb_head'] + '\n'.join(out)


for k, t in enumerate(a['tasks'], 1):
    rec = dict(file=t['id'], error='')
    try:
        torch.manual_seed(a['seed'])
        # B·C 요청 변환은 글만 넣음 (07과 같음)
        user = ([{'type': 'image', 'image': Image.open(t['image']).convert('RGB')}] if t.get('image') else []) + [
            {'type': 'text', 'text': t['prompt']}]
        messages = [{'role': 'system', 'content': [{'type': 'text', 'text': t['system']}]}, {'role': 'user', 'content': user}]
        torch.cuda.reset_peak_memory_stats()
        t1 = time.perf_counter()
        texts = gen(messages, sample=False)
        n_calls = 1
        final, probs = texts[0], probs_of(texts[0], t)
        first_probs = list(probs)
        fb_sent = ''
        if probs and t['kind'] in ('b', 'c'):
            # 07 R3 (가): 실패 이유를 알려 주고 샘플링으로 다시 요청 (최대 a['b_max_extra']번)
            torch.manual_seed(a['seed'])
            m = messages
            for _ in range(a['b_max_extra']):
                fb_sent = a['b_fb'] + '\n'.join('- ' + x for x in probs)
                m = m + [{'role': 'assistant', 'content': [{'type': 'text', 'text': final}]},
                         {'role': 'user', 'content': [{'type': 'text', 'text': fb_sent}]}]
                final = gen(m, sample=True)[0]
                n_calls += 1
                texts.append(final)
                probs = probs_of(final, t)
                if not probs:
                    break
        elif probs:
            # 샘플링 후보 n개 → 실패 항목이 가장 적은 후보
            cands = gen(messages, sample=True, n=a['n_cand'])
            n_calls += 1
            texts += cands
            n_bad, _, best = min((len(probs_of(c, t)), i, c) for i, c in enumerate(cands))
            if n_bad < len(probs):
                final, probs = best, probs_of(best, t)
            if probs:
                # 구체적 재요청: 가장 나은 글 + 실패 이유 + 고치는 방법
                fb_sent = feedback(probs, t['must'])
                m2 = messages + [{'role': 'assistant', 'content': [{'type': 'text', 'text': final}]},
                                 {'role': 'user', 'content': [{'type': 'text', 'text': fb_sent}]}]
                fix = gen(m2, sample=True)[0]
                n_calls += 1
                texts.append(fix)
                fp = probs_of(fix, t)
                if len(fp) < len(probs):
                    final, probs = fix, fp
        rec.update(sec=round(time.perf_counter() - t1, 2), peak_vram_gb=peak_now(), info=json.dumps(dict(
            text=final, problems=probs, first_problems=first_probs, fb_sent=fb_sent, n_gen=len(texts), n_calls=n_calls,
            texts_all=texts, gen_cfg=GEN_CFG), ensure_ascii=False))
    except Exception as e:
        rec['error'] = f'{type(e).__name__}: {e}'[:500]
    write(rec)
    log(f"문구 {k}/{len(a['tasks'])} {t['id']} {rec.get('sec')}초 {rec['error'][:120]}")
write_stage(load_sec)
"""

CHILD_C = r"""from compel import CompelForSDXL
from diffusers import EulerAncestralDiscreteScheduler, StableDiffusionXLPipeline

log('animagine 로드 시작')
t_load = time.perf_counter()
pipe = StableDiffusionXLPipeline.from_pretrained(a['model'], torch_dtype=torch.bfloat16)
pipe.load_ip_adapter(a['ipa']['repo'], subfolder=a['ipa']['subfolder'], weight_name=a['ipa']['weight_name'])
pipe.to('cuda')
pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)
pipe.set_progress_bar_config(disable=True)
compel = CompelForSDXL(pipe)
load_sec = round(time.perf_counter() - t_load, 2)
peak_now()
log(f'animagine 로드 끝 {load_sec}초')
for k, t in enumerate(a['tasks'], 1):
    rec = dict(file=t['file'], error='')
    try:
        extra = 0.0
        if t['lora']:
            t2 = time.perf_counter()
            log('LoRA 불러오기 ' + t['lora'])
            pipe.load_lora_weights(t['lora'], weight_name=t['lora_weight'], adapter_name='style')
            extra += time.perf_counter() - t2
        n_tok = len(pipe.tokenizer(t['prompt']).input_ids)
        torch.cuda.reset_peak_memory_stats()
        t1 = time.perf_counter()
        pipe.set_ip_adapter_scale(t['ipa_scale'])
        if t['compel']:
            e = compel(t['prompt'], negative_prompt=t['negative'])
            kw = dict(prompt_embeds=e.embeds, pooled_prompt_embeds=e.pooled_embeds, negative_prompt_embeds=e.negative_embeds,
                      negative_pooled_prompt_embeds=e.negative_pooled_embeds)
        else:
            kw = dict(prompt=t['prompt'], negative_prompt=t['negative'])
        img = pipe(**kw, ip_adapter_image=Image.open(t['ref']).convert('RGB'), width=t['w'], height=t['h'],
                   num_inference_steps=a['steps'], guidance_scale=a['cfg'], generator=torch.Generator('cpu').manual_seed(t['seed'])).images[0]
        img.save(t['out'])
        rec.update(sec=round(time.perf_counter() - t1, 2), peak_vram_gb=peak_now())
        if t['lora']:
            t2 = time.perf_counter()
            pipe.unload_lora_weights()
            extra += time.perf_counter() - t2
        rec.update(extra_sec=round(extra, 2), info=json.dumps(dict(n_tokens=n_tok, truncated=n_tok > pipe.tokenizer.model_max_length
                                                                   and not t['compel'])))
    except Exception as e:
        rec['error'] = f'{type(e).__name__}: {e}'[:300]
    write(rec)
    log(f"그림 {k}/{len(a['tasks'])} {t['file']} {rec.get('sec')}초 (LoRA {rec.get('extra_sec', 0)}초) {rec['error'][:100]}")
write_stage(load_sec)
"""

CHILD_SDXL = r"""from diffusers import StableDiffusionXLImg2ImgPipeline, StableDiffusionXLPipeline

log('SDXL base 로드 시작')
t_load = time.perf_counter()
pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(a['model'], torch_dtype=torch.bfloat16).to('cuda')
pipe.set_progress_bar_config(disable=True)
load_sec = round(time.perf_counter() - t_load, 2)
peak_now()
log(f'SDXL base 로드 끝 {load_sec}초')
n = len(a['tasks'])
for k, t in enumerate(a['tasks'], 1):
    rec = dict(file=t['file'], error='')
    try:
        torch.cuda.reset_peak_memory_stats()
        t1 = time.perf_counter()
        b = t['bg']
        t2i = StableDiffusionXLPipeline.from_pipe(pipe)
        out = t2i(prompt=b['prompt'], negative_prompt=b['negative'], num_inference_steps=b['steps'], guidance_scale=b['cfg'],
                  width=b['size'], height=b['size'], generator=torch.Generator('cpu').manual_seed(b['seed'])).images[0]
        del t2i
        out.save(t['out'])
        rec.update(sec=round(time.perf_counter() - t1, 2), peak_vram_gb=peak_now())
    except Exception as e:
        rec['error'] = f'{type(e).__name__}: {e}'[:300]
    write(rec)
    log(f"SDXL {k}/{n} {t['file']} {rec.get('sec')}초 {rec['error'][:100]}")
write_stage(load_sec)
"""

CHILD_MASK = r"""from torchvision import transforms
from transformers import AutoModelForImageSegmentation


def center_crop(im, w, h):
    # IC-Light 데모 resize_and_center_crop과 같은 방식 (16과 같음)
    s = max(w / im.width, h / im.height)
    rw, rh = int(round(im.width * s)), int(round(im.height * s))
    im = im.resize((rw, rh), Image.LANCZOS)
    return im.crop(((rw - w) / 2, (rh - h) / 2, (rw + w) / 2, (rh + h) / 2))


def d_frame(w0, h0):
    f = a['frame']
    s = f['ic_max_side'] / max(w0, h0)
    w, h = int(round(w0 * s / 64)) * 64, int(round(h0 * s / 64)) * 64
    W, H = int(round(w * f['highres_scale'] / 64)) * 64, int(round(h * f['highres_scale'] / 64)) * 64
    s2 = f['max_side'] / max(W, H)
    return int(round(W * s2 / 8)) * 8, int(round(H * s2 / 8)) * 8


log('BiRefNet 로드 시작')
t_load = time.perf_counter()
model = AutoModelForImageSegmentation.from_pretrained(a['repo'], trust_remote_code=True).to('cuda').eval().float()
tf = transforms.Compose([transforms.Resize((1024, 1024)), transforms.ToTensor(),
                         transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
load_sec = round(time.perf_counter() - t_load, 2)
peak_now()
log(f'BiRefNet 로드 끝 {load_sec}초')
for k, t in enumerate(a['tasks'], 1):
    rec = dict(file=t['file'], error='')
    try:
        torch.cuda.reset_peak_memory_stats()
        t1 = time.perf_counter()
        im = Image.open(t['source_path']).convert('RGB')
        # 14 load_goods와 같음: 긴 변 1024(8의 배수). 목업은 이미 이 크기라 그대로
        s = a['frame']['max_side'] / max(im.size)
        img = im.resize((int(round(im.width * s / 8)) * 8, int(round(im.height * s / 8)) * 8), Image.LANCZOS)
        with torch.no_grad():
            pred = model(tf(img).unsqueeze(0).to('cuda'))[-1].sigmoid()[0, 0].float().cpu().numpy()
        m = Image.fromarray((pred * 255).astype(np.uint8)).resize(img.size, Image.BILINEAR)
        m.save(t['mask_full_out'])
        w, h = d_frame(*img.size) if t['crop'] else img.size
        center_crop(img, w, h).save(t['goods_out'])
        cm = center_crop(m, w, h)
        cm.save(t['mask_out'])
        rec.update(sec=round(time.perf_counter() - t1, 2), peak_vram_gb=peak_now(), info=json.dumps(dict(
            source_size=list(im.size), in_size=list(img.size), frame=[w, h],
            mask_area=round(float((np.asarray(cm, dtype=np.float32) / 255 > 0.5).mean()), 4))))
    except Exception as e:
        rec['error'] = f'{type(e).__name__}: {e}'[:300]
    write(rec)
    log(f"마스크 {k}/{len(a['tasks'])} {t['file']} {rec.get('sec')}초 {rec['error'][:100]}")
write_stage(load_sec)
"""

CHILD_Y = r"""from PIL import ImageOps


def resize_with_padding(img, expected_size):
    # 모델 카드 코드 그대로
    img.thumbnail((expected_size[0], expected_size[1]))
    delta_width = expected_size[0] - img.size[0]
    delta_height = expected_size[1] - img.size[1]
    pad_width = delta_width // 2
    pad_height = delta_height // 2
    padding = (pad_width, pad_height, delta_width - pad_width, delta_height - pad_height)
    return ImageOps.expand(img, padding), padding


def band(path):
    # 20과 같음: 가장자리별 띠 폭(px)과 판정. 띠: 가장자리 EDGE_PX 밝기 평균 < DARK, 전체 평균 > 60
    x = np.asarray(Image.open(path).convert('L'), dtype=np.float32)
    cols, rows = x.mean(0), x.mean(1)
    out = dict(mean=round(float(x.mean()), 1))
    for side, v in [('left', cols), ('right', cols[::-1]), ('top', rows), ('bottom', rows[::-1])]:
        dark = v < a['dark']
        out[f'{side}_px'] = int(len(dark) if dark.all() else np.argmin(dark))
        out[f'{side}_band'] = bool(v[:a['edge_px']].mean() < a['dark'] and x.mean() > 60)
    out['band'] = any(out[f'{s}_band'] for s in ['left', 'right', 'top', 'bottom'])
    return out


# 저장소 pipeline.py(diffusers 0.27 기준)의 옛 경로 → 현재 diffusers의 같은 모듈
import diffusers.models.controlnets.multicontrolnet as _mc
sys.modules.setdefault('diffusers.pipelines.controlnet.multicontrolnet', _mc)
from diffusers import DiffusionPipeline

log('Y 로드 시작')
t_load = time.perf_counter()
pipe = DiffusionPipeline.from_pretrained(a['repo'], custom_pipeline=a['repo'], trust_remote_code=True).to('cuda')
pipe.set_progress_bar_config(disable=True)
load_sec = round(time.perf_counter() - t_load, 2)
peak_now()
log(f'Y 로드 끝 {load_sec}초 | {type(pipe).__name__}')
S = a['size']
for k, t in enumerate(a['tasks'], 1):
    rec = dict(file=t['file'], error='')
    try:
        goods = Image.open(t['goods_path']).convert('RGB')
        fg = Image.open(t['mask_path']).convert('L')
        img, pad = resize_with_padding(goods.copy(), (S, S))
        m, _ = resize_with_padding(fg.copy(), (S, S))
        mask = ImageOps.invert(m)
        al = np.asarray(fg, dtype=np.float32)[..., None] / 255
        torch.cuda.reset_peak_memory_stats()
        tries, total = [], 0.0
        for seed in a['seeds']:
            t1 = time.perf_counter()
            g = torch.Generator(device='cuda').manual_seed(seed)
            with torch.autocast('cuda'):
                out = pipe(prompt=t['prompt'], image=img, mask_image=mask, control_image=mask, num_images_per_prompt=1, generator=g,
                           num_inference_steps=a['steps'], guess_mode=a['guess_mode'],
                           controlnet_conditioning_scale=a['cond_scale']).images[0]
            out.save(t['raw_tpl'].format(seed=seed))
            # 패딩을 걷어내고 원래 틀로 키운 뒤 원본 굿즈를 마스크 알파로 다시 덮어씀
            box = (pad[0], pad[1], S - pad[2], S - pad[3])
            big = np.asarray(out.crop(box).resize(goods.size, Image.LANCZOS), dtype=np.float32)
            res = np.asarray(goods, dtype=np.float32) * al + big * (1 - al)
            p = t['try_tpl'].format(seed=seed)
            Image.fromarray(res.round().clip(0, 255).astype(np.uint8)).save(p)
            b = band(p)
            sec = round(time.perf_counter() - t1, 2)
            total += sec
            tries.append(dict(seed=seed, sec=sec, **b))
            log(f"Y {k}/{len(a['tasks'])} {t['file']} seed {seed} {sec}초 띠 {'있음' if b['band'] else '없음'}")
            if not b['band']:
                break
        # 띠 없는 첫 결과, 3번 모두 띠면 마지막 결과
        Image.open(t['try_tpl'].format(seed=tries[-1]['seed'])).save(t['out'])
        rec.update(sec=round(total, 2), peak_vram_gb=peak_now(), info=json.dumps(dict(
            tries=tries, n_tries=len(tries), used_seed=tries[-1]['seed'], band_final=tries[-1]['band'])))
    except Exception as e:
        rec['error'] = f'{type(e).__name__}: {e}'[:300]
    write(rec)
write_stage(load_sec)
"""

CHILD_IC = r"""import math

import safetensors.torch as sf
import torch.nn.functional as F
from diffusers import AutoencoderKL, DPMSolverMultistepScheduler, StableDiffusionImg2ImgPipeline, StableDiffusionPipeline, UNet2DConditionModel
from diffusers.models.attention_processor import AttnProcessor2_0
from huggingface_hub import hf_hub_download
from PIL import ImageFilter
from transformers import CLIPTextModel, CLIPTokenizer

SD15, ICLIGHT = a['sd15'], a['iclight']
RATIO_CLIP = tuple(a['ratio_clip'])


# 15 "D2 IC-Light 배경 조건 재조명" 셀과 같은 코드 (IC-Light 공식 데모 gradio_demo_bg.py 커밋 bcf3f29)
def load_iclight():
    tokenizer = CLIPTokenizer.from_pretrained(SD15, subfolder='tokenizer')
    text_encoder = CLIPTextModel.from_pretrained(SD15, subfolder='text_encoder')
    vae = AutoencoderKL.from_pretrained(SD15, subfolder='vae')
    unet = UNet2DConditionModel.from_pretrained(SD15, subfolder='unet')
    with torch.no_grad():
        new_conv_in = torch.nn.Conv2d(12, unet.conv_in.out_channels, unet.conv_in.kernel_size, unet.conv_in.stride, unet.conv_in.padding)
        new_conv_in.weight.zero_()
        new_conv_in.weight[:, :4, :, :].copy_(unet.conv_in.weight)
        new_conv_in.bias = unet.conv_in.bias
        unet.conv_in = new_conv_in
    unet_original_forward = unet.forward

    def hooked_unet_forward(sample, timestep, encoder_hidden_states, **kwargs):
        c_concat = kwargs['cross_attention_kwargs']['concat_conds'].to(sample)
        c_concat = torch.cat([c_concat] * (sample.shape[0] // c_concat.shape[0]), dim=0)
        new_sample = torch.cat([sample, c_concat], dim=1)
        kwargs['cross_attention_kwargs'] = {}
        return unet_original_forward(new_sample, timestep, encoder_hidden_states, **kwargs)

    unet.forward = hooked_unet_forward
    sd_offset = sf.load_file(hf_hub_download(ICLIGHT['repo'], ICLIGHT['file']))
    sd_origin = unet.state_dict()
    unet.load_state_dict({k: sd_origin[k] + sd_offset[k] for k in sd_origin.keys()}, strict=True)
    del sd_offset, sd_origin
    text_encoder = text_encoder.to(device='cuda', dtype=torch.float16)
    vae = vae.to(device='cuda', dtype=torch.bfloat16)
    unet = unet.to(device='cuda', dtype=torch.float16)
    unet.set_attn_processor(AttnProcessor2_0())
    vae.set_attn_processor(AttnProcessor2_0())
    sched = DPMSolverMultistepScheduler(num_train_timesteps=1000, beta_start=0.00085, beta_end=0.012,
                                        algorithm_type='sde-dpmsolver++', use_karras_sigmas=True, steps_offset=1)
    kw = dict(vae=vae, text_encoder=text_encoder, tokenizer=tokenizer, unet=unet, scheduler=sched, safety_checker=None,
              requires_safety_checker=False, feature_extractor=None, image_encoder=None)
    return tokenizer, text_encoder, vae, StableDiffusionPipeline(**kw), StableDiffusionImg2ImgPipeline(**kw)


@torch.inference_mode()
def encode_prompt_inner(txt):
    max_length = tokenizer.model_max_length
    chunk_length = tokenizer.model_max_length - 2
    id_start, id_end = tokenizer.bos_token_id, tokenizer.eos_token_id

    def pad(x, p, i):
        return x[:i] if len(x) >= i else x + [p] * (i - len(x))

    tokens = tokenizer(txt, truncation=False, add_special_tokens=False)['input_ids']
    chunks = [[id_start] + tokens[i: i + chunk_length] + [id_end] for i in range(0, len(tokens), chunk_length)]
    chunks = [pad(ck, id_end, max_length) for ck in chunks]
    return text_encoder(torch.tensor(chunks).to(device='cuda', dtype=torch.int64)).last_hidden_state


@torch.inference_mode()
def encode_prompt_pair(positive_prompt, negative_prompt):
    c, uc = encode_prompt_inner(positive_prompt), encode_prompt_inner(negative_prompt)
    max_count = max(float(len(c)), float(len(uc)))
    max_chunk = max(len(c), len(uc))
    c = torch.cat([c] * int(math.ceil(max_count / len(c))), dim=0)[:max_chunk]
    uc = torch.cat([uc] * int(math.ceil(max_count / len(uc))), dim=0)[:max_chunk]
    return torch.cat([p[None, ...] for p in c], dim=1), torch.cat([p[None, ...] for p in uc], dim=1)


@torch.inference_mode()
def pytorch2numpy(imgs, quant=True):
    out = []
    for x in imgs:
        y = x.movedim(0, -1)
        if quant:
            out.append((y * 127.5 + 127.5).detach().float().cpu().numpy().clip(0, 255).astype(np.uint8))
        else:
            out.append((y * 0.5 + 0.5).detach().float().cpu().numpy().clip(0, 1).astype(np.float32))
    return out


@torch.inference_mode()
def numpy2pytorch(imgs):
    return (torch.from_numpy(np.stack(imgs, axis=0)).float() / 127.0 - 1.0).movedim(-1, 1)


def resize_and_center_crop(image, tw, th):
    pil = Image.fromarray(image)
    s = max(tw / pil.width, th / pil.height)
    rw, rh = int(round(pil.width * s)), int(round(pil.height * s))
    pil = pil.resize((rw, rh), Image.LANCZOS)
    return np.array(pil.crop(((rw - tw) / 2, (rh - th) / 2, (rw + tw) / 2, (rh + th) / 2)))


def resize_without_crop(image, tw, th):
    return np.array(Image.fromarray(image).resize((tw, th), Image.LANCZOS))


@torch.inference_mode()
def process(input_fg, input_bg, prompt, w, h, seed, steps, a_prompt, n_prompt, cfg, highres_scale, highres_denoise):
    rng = torch.Generator(device='cuda').manual_seed(seed)
    fg, bg = resize_and_center_crop(input_fg, w, h), resize_and_center_crop(input_bg, w, h)
    cc = vae.encode(numpy2pytorch([fg, bg]).to(device=vae.device, dtype=vae.dtype)).latent_dist.mode() * vae.config.scaling_factor
    cc = torch.cat([c[None, ...] for c in cc], dim=1)
    conds, unconds = encode_prompt_pair(prompt + ', ' + a_prompt, n_prompt)
    latents = t2i_pipe(prompt_embeds=conds, negative_prompt_embeds=unconds, width=w, height=h, num_inference_steps=steps,
                       num_images_per_prompt=1, generator=rng, output_type='latent', guidance_scale=cfg,
                       cross_attention_kwargs={'concat_conds': cc}).images.to(vae.dtype) / vae.config.scaling_factor
    pixels = pytorch2numpy(vae.decode(latents).sample)
    pixels = [resize_without_crop(p, int(round(w * highres_scale / 64.0) * 64), int(round(h * highres_scale / 64.0) * 64)) for p in pixels]
    latents = vae.encode(numpy2pytorch(pixels).to(device=vae.device, dtype=vae.dtype)).latent_dist.mode() * vae.config.scaling_factor
    latents = latents.to(device=t2i_pipe.unet.device, dtype=t2i_pipe.unet.dtype)
    h2, w2 = latents.shape[2] * 8, latents.shape[3] * 8
    fg, bg = resize_and_center_crop(input_fg, w2, h2), resize_and_center_crop(input_bg, w2, h2)
    cc = vae.encode(numpy2pytorch([fg, bg]).to(device=vae.device, dtype=vae.dtype)).latent_dist.mode() * vae.config.scaling_factor
    cc = torch.cat([c[None, ...] for c in cc], dim=1)
    latents = i2i_pipe(image=latents, strength=highres_denoise, prompt_embeds=conds, negative_prompt_embeds=unconds, width=w2,
                       height=h2, num_inference_steps=int(round(steps / highres_denoise)), num_images_per_prompt=1, generator=rng,
                       output_type='latent', guidance_scale=cfg,
                       cross_attention_kwargs={'concat_conds': cc}).images.to(vae.dtype) / vae.config.scaling_factor
    return pytorch2numpy(vae.decode(latents).sample, quant=False)[0]


def blur(x, sigma, pad='reflect'):
    # 분리형 가우시안 (x: H×W×C float), 17과 같음
    r = int(3 * sigma)
    k = torch.exp(-(torch.arange(-r, r + 1, dtype=torch.float32) ** 2) / (2 * sigma ** 2))
    k = k / k.sum()
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    t = torch.from_numpy(np.ascontiguousarray(x.transpose(2, 0, 1)))[:, None].to(dev)
    k = k.to(dev)
    t = F.conv2d(F.pad(t, (r, r, 0, 0), mode=pad), k.view(1, 1, 1, -1))
    t = F.conv2d(F.pad(t, (0, 0, r, r), mode=pad), k.view(1, 1, -1, 1))
    return t[:, 0].cpu().numpy().transpose(1, 2, 0)


def masked_blur(x, al, sigma):
    # 굿즈 안쪽 값만으로 흐림 (정규화 합성곱), 16과 같음
    return blur(x * al[..., None], sigma) / np.maximum(blur(al[..., None], sigma), 1e-4)


def luma(x):
    return (x @ np.array([0.299, 0.587, 0.114], dtype=np.float32))[..., None]


def relight_n(goods, al, ic, sigma):
    # 16 R1n과 같은 식: 밝기 비율을 굿즈 안(알파 가중) 평균으로 나눠 전체 밝기는 원본 유지
    ratio = (masked_blur(luma(ic), al, sigma) + 1e-3) / (masked_blur(luma(goods), al, sigma) + 1e-3)
    mean = float((ratio[..., 0] * al).sum() / max(al.sum(), 1e-6))
    return (goods * np.clip(ratio / mean, *RATIO_CLIP)).clip(0, 1)


def fill_hole(img, al):
    # 17과 같음: 굿즈 자리(마스크 넓힘)를 주변 배경으로 메움 (1/8 크기에서 작은 흐림부터 큰 흐림 순으로 값이 있는 곳을 채움)
    hole = np.asarray(Image.fromarray(((al > 0.5) * 255).astype(np.uint8)).filter(
        ImageFilter.MaxFilter(2 * a['fill_dilate_px'] + 1)), dtype=np.float32) / 255
    h, w = hole.shape
    sw, sh = max(w // 8, 8), max(h // 8, 8)
    small = np.asarray(Image.fromarray((img * 255).astype(np.uint8)).resize((sw, sh), Image.BOX), dtype=np.float32) / 255
    keep = 1 - np.asarray(Image.fromarray((hole * 255).astype(np.uint8)).resize((sw, sh), Image.BOX), dtype=np.float32) / 255
    keep = (keep > 0.99).astype(np.float32)
    est, have = small * keep[..., None], keep.copy()
    for s in [1, 2, 4, 8, 16, 32]:
        den = blur(keep[..., None], s, pad='replicate')[..., 0]
        e = blur(small * keep[..., None], s, pad='replicate') / np.maximum(den, 1e-6)[..., None]
        new = (have == 0) & (den > 0.02)
        est[new], have[new] = e[new], 1
    # 채운 순서에 따라 생기는 계단 무늬를 줄이려고 메운 부분만 한 번 더 흐림
    est = np.where(keep[..., None] > 0, est, blur(est, 3, pad='replicate'))
    big = np.asarray(Image.fromarray((est.clip(0, 1) * 255).round().astype(np.uint8)).resize((w, h), Image.BICUBIC),
                     dtype=np.float32) / 255
    m = np.asarray(Image.fromarray((hole * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(4)), dtype=np.float32)[..., None] / 255
    return img * (1 - m) + big * m


def arr(p):
    return np.asarray(Image.open(p).convert('RGB'), dtype=np.float32) / 255


log('IC-Light 로드 시작')
t_load = time.perf_counter()
tokenizer, text_encoder, vae, t2i_pipe, i2i_pipe = load_iclight()
t2i_pipe.set_progress_bar_config(disable=True)
i2i_pipe.set_progress_bar_config(disable=True)
load_sec = round(time.perf_counter() - t_load, 2)
peak_now()
log(f'IC-Light 로드 끝 {load_sec}초')
D = a['d2']
for k, t in enumerate(a['tasks'], 1):
    rec = dict(file=t['file'], error='')
    try:
        torch.cuda.reset_peak_memory_stats()
        t1 = time.perf_counter()
        goods = arr(t['goods_path'])
        al = np.asarray(Image.open(t['mask_path']).convert('L'), dtype=np.float32) / 255
        fill_sec = 0.0
        if t['opt'] == 'YR1n':
            ybg = arr(t['y_path'])
            cond = fill_hole(ybg, al)
            Image.fromarray((cond * 255).round().clip(0, 255).astype(np.uint8)).save(t['fill_out'])
            fill_sec = time.perf_counter() - t1
        else:
            cond = arr(t['bg_path'])
        t2 = time.perf_counter()
        h0, w0 = al.shape
        s = D['max_side'] / max(w0, h0)
        w, h = int(round(w0 * s / 64)) * 64, int(round(h0 * s / 64)) * 64
        # 데모 run_rmbg와 같은 회색(127) 배경 전경 (15·17과 같음)
        fg = (127 + (goods * 255 - 127) * al[..., None]).clip(0, 255).astype(np.uint8)
        res = process(fg, (cond * 255).round().astype(np.uint8), t['prompt'], w, h, a['seed'], D['steps'], D['a_prompt'], D['n_prompt'],
                      D['cfg'], D['highres_scale'], D['highres_denoise'])
        Image.fromarray((res * 255).clip(0, 255).astype(np.uint8)).save(t['ic_out'])
        ic_sec = time.perf_counter() - t2
        t3 = time.perf_counter()
        ic = np.asarray(Image.open(t['ic_out']).convert('RGB').resize((w0, h0), Image.LANCZOS), dtype=np.float32) / 255
        fgr = relight_n(goods, al, ic, t['sigma'])
        base = ic if t['base'] == 'ic' else ybg
        am = al[..., None]
        Image.fromarray(((fgr * am + base * (1 - am)) * 255).round().clip(0, 255).astype(np.uint8)).save(t['out'])
        rel_sec = time.perf_counter() - t3
        rec.update(sec=round(time.perf_counter() - t1, 2), peak_vram_gb=peak_now(), info=json.dumps(dict(
            fill_sec=round(fill_sec, 2), ic_sec=round(ic_sec, 2), relight_sec=round(rel_sec, 2), ic_w=w, ic_h=h)))
    except Exception as e:
        rec['error'] = f'{type(e).__name__}: {e}'[:300]
    write(rec)
    log(f"IC-Light {k}/{len(a['tasks'])} {t['file']} {rec.get('sec')}초 {rec['error'][:100]}")
write_stage(load_sec)
"""

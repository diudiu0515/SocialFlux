FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY environment/ environment/
COPY evaluation/ evaluation/
COPY offline/ offline/
COPY pipeline/ pipeline/
COPY policies/ policies/
COPY prompts/ prompts/
COPY providers/ providers/
COPY rollout/ rollout/
COPY scenario_design/ scenario_design/
COPY schemas/ schemas/
COPY shared/ shared/
COPY tasks/ tasks/
COPY configs/ configs/
COPY docs/ docs/
COPY reports/ reports/
COPY reviews/ reviews/
COPY web/ web/
COPY scripts/serve_independent_lab.py scripts/serve_independent_lab.py
COPY DESIGN_CONTRACT.md PROJECT_PROGRESS.md self_check.md ./
RUN python -S -c "import web.server" && mkdir -p /root/.ssh && chmod 0700 /root/.ssh
CMD ["python", "-u", "scripts/serve_independent_lab.py"]

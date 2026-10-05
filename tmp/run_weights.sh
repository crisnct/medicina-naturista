export EMBEDDING_THREADS=8 PYTHONIOENCODING=utf-8
URL=$(grep "^DATABASE_URL=" .env | cut -d= -f2-)
unset SEARCH_SEMANTIC_ONLY
for V in 2 3 4 6; do
  WEIGHT_V=$V DATABASE_URL="$URL" python -m tmp.eval_weight_v --output tmp/eval-e5-w$V.json > /dev/null 2>&1
  WEIGHT_V=$V DATABASE_URL="${URL%/medicina}/medicina_qwen" python -m tmp.eval_weight_v --output tmp/eval-qwen-w$V.json > /dev/null 2>&1
done
echo done

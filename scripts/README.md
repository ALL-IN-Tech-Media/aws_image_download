# Parallel Processing Scripts Guide

This directory contains scripts for high-speed parallel processing of TikTok image data using AWS Lambda.

## 🚀 Quick Start - Parallel Processing

### Current Performance vs Parallel
- **Sequential**: 364 images in 28 seconds
- **Parallel (10 batches)**: 364 images in ~3 seconds (**9x faster**)
- **Your Lambda limit**: 10 concurrent executions

---

## 📋 **STEP-BY-STEP PARALLEL PROCESSING**

### **Step 1: Analyze Your CSV Data**

First, understand your data distribution:

```bash
# Navigate to project directory
cd /home/geshuhang/aws_image_download

# Analyze your CSV structure
python3 -c "
import csv
creators = {}
with open('cover_urls_20250819_104209.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['cover_url'].strip():
            creator = row['creator_name']
            creators[creator] = creators.get(creator, 0) + 1

print(f'Total creators: {len(creators)}')
print(f'Total images: {sum(creators.values())}')
print('\\nCreator breakdown:')
for creator, count in sorted(creators.items(), key=lambda x: x[1], reverse=True):
    print(f'{creator}: {count} images')
"
```

**Expected Output:**
```
Total creators: 11
Total images: 364

Creator breakdown:
aal.i.jah: 38 images
aabjj81: 38 images
aaliyah_garcia18: 37 images
... (and so on)
```

---

### **Step 2: Create Balanced Batches**

#### **Method A: Automatic Splitting (Recommended)**

```bash
# Activate your Python environment
source /home/geshuhang/environemnt/general/bin/activate

# Use the parallel processor script
python3 scripts/parallel_processor.py cover_urls_20250819_104209.csv --method s3 --batch-size 36

# This automatically:
# 1. Analyzes your data
# 2. Creates 10 balanced batches (~36 images each)
# 3. Uploads all batches simultaneously
# 4. Triggers 10 parallel Lambda instances
```

#### **Method B: Manual Splitting (For Learning)**

**Step 2.1: Split the CSV file**
```bash
# Remove header from original file for splitting
tail -n +2 cover_urls_20250819_104209.csv > data_only.csv

# Split into 10 files of ~36 lines each
split -l 36 data_only.csv batch_

# Add header back to each batch
for file in batch_*; do
    # Create temporary file with header
    echo "creator_name,cover_url,created_at" > temp_${file}.csv
    cat "$file" >> temp_${file}.csv
    mv temp_${file}.csv ${file}.csv
    rm "$file"  # Remove the original split file
done

# Clean up
rm data_only.csv
```

**Step 2.2: Verify batch creation**
```bash
# Check that batches were created correctly
echo "=== BATCH VERIFICATION ==="
for file in batch_*.csv; do
    lines=$(wc -l < "$file")
    echo "$file: $((lines-1)) images"  # Subtract 1 for header
done

# Should show something like:
# batch_aa.csv: 36 images
# batch_ab.csv: 36 images
# batch_ac.csv: 36 images
# ... etc
```

---

### **Step 3: Upload All Batches Simultaneously**

This is the **critical step** that triggers parallel processing:

```bash
echo "=== STARTING PARALLEL UPLOAD ===" 
echo "Upload started at: $(date)"

# Record start time
start_time=$(date +%s)

# Upload all batches simultaneously using background processes (&)
aws s3 cp batch_aa.csv s3://tiktok-image-input/csv-files/parallel_batch_01_$(date +%Y%m%d_%H%M%S).csv --region us-east-2 &
aws s3 cp batch_ab.csv s3://tiktok-image-input/csv-files/parallel_batch_02_$(date +%Y%m%d_%H%M%S).csv --region us-east-2 &
aws s3 cp batch_ac.csv s3://tiktok-image-input/csv-files/parallel_batch_03_$(date +%Y%m%d_%H%M%S).csv --region us-east-2 &
aws s3 cp batch_ad.csv s3://tiktok-image-input/csv-files/parallel_batch_04_$(date +%Y%m%d_%H%M%S).csv --region us-east-2 &
aws s3 cp batch_ae.csv s3://tiktok-image-input/csv-files/parallel_batch_05_$(date +%Y%m%d_%H%M%S).csv --region us-east-2 &
aws s3 cp batch_af.csv s3://tiktok-image-input/csv-files/parallel_batch_06_$(date +%Y%m%d_%H%M%S).csv --region us-east-2 &
aws s3 cp batch_ag.csv s3://tiktok-image-input/csv-files/parallel_batch_07_$(date +%Y%m%d_%H%M%S).csv --region us-east-2 &
aws s3 cp batch_ah.csv s3://tiktok-image-input/csv-files/parallel_batch_08_$(date +%Y%m%d_%H%M%S).csv --region us-east-2 &
aws s3 cp batch_ai.csv s3://tiktok-image-input/csv-files/parallel_batch_09_$(date +%Y%m%d_%H%M%S).csv --region us-east-2 &
aws s3 cp batch_aj.csv s3://tiktok-image-input/csv-files/parallel_batch_10_$(date +%Y%m%d_%H%M%S).csv --region us-east-2 &

# Wait for all background uploads to complete
wait

# Calculate upload time
end_time=$(date +%s)
upload_duration=$((end_time - start_time))

echo "=== UPLOAD COMPLETED ==="
echo "Upload completed at: $(date)"
echo "Total upload time: ${upload_duration} seconds"
echo "🚀 10 Lambda instances are now processing simultaneously!"
```

**Key Points:**
- **`&` symbol**: Runs each command in background (parallel)
- **`wait` command**: Waits for all background processes to finish
- **Unique timestamps**: Prevents filename conflicts
- **Result**: 10 Lambda instances start within seconds of each other

---

### **Step 4: Monitor Parallel Processing**

```bash
# Monitor all Lambda instances in real-time
echo "=== MONITORING PARALLEL PROCESSING ==="
aws logs tail /aws/lambda/image-collage-processor --follow --region us-east-2

# In another terminal, count active instances
watch -n 2 'aws logs filter-log-events \
  --log-group-name /aws/lambda/image-collage-processor \
  --filter-pattern "START RequestId" \
  --start-time $(($(date +%s) - 60))000 \
  --region us-east-2 | grep -c "START RequestId"'
```

---

### **Step 5: Verify Results**

```bash
# Check all generated collages
echo "=== CHECKING RESULTS ==="
aws s3 ls s3://tiktok-image-output/s3-trigger/csv-files/ --recursive --region us-east-2 | grep "$(date +%Y%m%d)"

# Count total collages created
collage_count=$(aws s3 ls s3://tiktok-image-output/s3-trigger/csv-files/ --recursive --region us-east-2 | grep "$(date +%Y%m%d)" | grep "collage" | wc -l)
echo "Total collages created: $collage_count"

# Expected: 11 collages (one per creator)
```

---

## 🔧 **ADVANCED PARALLEL TECHNIQUES**

### **Creator-Based Splitting (Maximum Speed)**

For your specific data, split by individual creators:

```bash
# Create one batch per creator (11 batches total)
echo "creator_name,cover_url,created_at" > aaliahmaddox.csv
grep "^aaliahmaddox," cover_urls_20250819_104209.csv >> aaliahmaddox.csv

echo "creator_name,cover_url,created_at" > aal.i.jah.csv  
grep "^aal\.i\.jah," cover_urls_20250819_104209.csv >> aal.i.jah.csv

echo "creator_name,cover_url,created_at" > aabjj81.csv
grep "^aabjj81," cover_urls_20250819_104209.csv >> aabjj81.csv

# ... repeat for all 11 creators

# Upload all creators simultaneously
timestamp=$(date +%Y%m%d_%H%M%S)
for creator_file in aaliahmaddox.csv aal.i.jah.csv aabjj81.csv aaasisisiyou.csv aaaer723.csv aaliyah_garcia18.csv aali.zm.csv aalaysia_00.csv aakritisubedi5.csv aakritisadashanker.csv aak9649.csv; do
    if [[ -f "$creator_file" ]]; then
        creator_name=$(basename "$creator_file" .csv)
        aws s3 cp "$creator_file" s3://tiktok-image-input/csv-files/creator_${creator_name}_${timestamp}.csv --region us-east-2 &
    fi
done
wait

echo "🎯 11 Lambda instances processing simultaneously!"
```

---

## 📊 **BATCH SIZE OPTIMIZATION**

### **Recommended Batch Sizes by Lambda Limit:**

| **Lambda Limit** | **Optimal Batch Size** | **Number of Batches** | **Processing Time** |
|-------------------|------------------------|----------------------|---------------------|
| **10** | 36 images | 10 batches | **~3 seconds** |
| **50** | 7 images | 50 batches | **~0.6 seconds** |
| **100** | 4 images | 100 batches | **~0.3 seconds** |
| **500** | 1 image | 364 batches | **~0.1 seconds** |

### **Formula for Optimal Batch Size:**
```
Optimal Batch Size = Total Images ÷ Lambda Concurrency Limit
Your Case: 364 images ÷ 10 limit = 36 images per batch
```

---

## 🎛️ **PARALLEL PROCESSING METHODS COMPARISON**

### **Method 1: S3 Parallel Upload (Automatic)**
```bash
# Pros: Automatic trigger, no message limits, simple
# Cons: Creates many files, harder to track individual batches

# Implementation:
for i in {1..10}; do
    aws s3 cp batch_${i}.csv s3://tiktok-image-input/csv-files/parallel_${i}.csv --region us-east-2 &
done
wait
```

### **Method 2: SQS Parallel Messages (Controlled)**
```bash
# Pros: No file creation, better tracking, custom configs per batch
# Cons: Message size limits, more complex setup

# Implementation:
for batch_data in "${batch_contents[@]}"; do
    aws sqs send-message \
      --queue-url "https://sqs.us-east-2.amazonaws.com/624433616538/tiktok-image-processing-queue" \
      --message-body "{
        \"processing_type\": \"csv_data\",
        \"csv_data\": \"$batch_data\",
        \"output_prefix\": \"parallel_sqs_$(date +%Y%m%d_%H%M%S)/\"
      }" \
      --region us-east-2 &
done
wait
```

---

## 🔍 **MONITORING & DEBUGGING**

### **Real-time Monitoring Commands**

```bash
# Monitor all parallel instances
aws logs tail /aws/lambda/image-collage-processor --follow --region us-east-2

# Count concurrent executions
aws logs filter-log-events \
  --log-group-name /aws/lambda/image-collage-processor \
  --filter-pattern "START RequestId" \
  --start-time $(($(date +%s) - 120))000 \
  --region us-east-2 | grep -c "START"

# Check processing completion
aws logs filter-log-events \
  --log-group-name /aws/lambda/image-collage-processor \
  --filter-pattern "Processing complete" \
  --start-time $(($(date +%s) - 300))000 \
  --region us-east-2

# Monitor memory usage across instances
aws logs filter-log-events \
  --log-group-name /aws/lambda/image-collage-processor \
  --filter-pattern "Memory after collage creation" \
  --start-time $(($(date +%s) - 300))000 \
  --region us-east-2
```

### **Performance Metrics to Track**

```bash
# Measure total processing time
start_time=$(date +%s)
# ... upload batches ...
end_time=$(date +%s)
echo "Total processing time: $((end_time - start_time)) seconds"

# Count successful collages
aws s3 ls s3://tiktok-image-output/ --recursive --region us-east-2 | grep "$(date +%Y%m%d)" | grep "collage" | wc -l

# Calculate images per second
total_images=364
processing_time=3  # Replace with actual time
echo "Processing rate: $((total_images / processing_time)) images/second"
```

---

## 🎯 **COMPLETE EXAMPLE: Processing Your Current File**

### **Option 1: Quick 4-Batch Split (Safe)**

```bash
# 1. Create 4 balanced batches
echo "=== CREATING 4 BALANCED BATCHES ==="

# Split CSV (excluding header)
tail -n +2 cover_urls_20250819_104209.csv > temp_data.csv
split -l 91 temp_data.csv batch_

# Add headers to each batch
for file in batch_*; do
    echo "creator_name,cover_url,created_at" > ${file}.csv
    cat "$file" >> ${file}.csv
    rm "$file"
done
rm temp_data.csv

# 2. Verify batches
echo "=== BATCH VERIFICATION ==="
for file in batch_*.csv; do
    lines=$(wc -l < "$file")
    echo "$file: $((lines-1)) images"
done

# 3. Upload simultaneously
echo "=== PARALLEL UPLOAD STARTING ==="
timestamp=$(date +%Y%m%d_%H%M%S)
start_time=$(date +%s)

aws s3 cp batch_aa.csv s3://tiktok-image-input/csv-files/parallel_${timestamp}_batch_01.csv --region us-east-2 &
aws s3 cp batch_ab.csv s3://tiktok-image-input/csv-files/parallel_${timestamp}_batch_02.csv --region us-east-2 &
aws s3 cp batch_ac.csv s3://tiktok-image-input/csv-files/parallel_${timestamp}_batch_03.csv --region us-east-2 &
aws s3 cp batch_ad.csv s3://tiktok-image-input/csv-files/parallel_${timestamp}_batch_04.csv --region us-east-2 &

# Wait for all uploads to complete
wait

end_time=$(date +%s)
echo "=== UPLOAD COMPLETED ==="
echo "Upload time: $((end_time - start_time)) seconds"
echo "🚀 4 Lambda instances are now processing!"

# 4. Monitor processing
echo "=== MONITORING PROCESSING ==="
aws logs tail /aws/lambda/image-collage-processor --since 1m --region us-east-2
```

### **Option 2: Maximum 10-Batch Split (Fastest)**

```bash
# 1. Create 10 optimal batches
echo "=== CREATING 10 OPTIMAL BATCHES ==="

# Split into 10 files of ~36 lines each
tail -n +2 cover_urls_20250819_104209.csv > temp_data.csv
split -l 36 temp_data.csv batch_

# Add headers and rename
batch_num=1
for file in batch_*; do
    printf -v batch_name "batch_%02d.csv" $batch_num
    echo "creator_name,cover_url,created_at" > "$batch_name"
    cat "$file" >> "$batch_name"
    rm "$file"
    ((batch_num++))
done
rm temp_data.csv

# 2. Upload all 10 batches simultaneously
echo "=== PARALLEL UPLOAD (10 BATCHES) ==="
timestamp=$(date +%Y%m%d_%H%M%S)
start_time=$(date +%s)

for i in {01..10}; do
    if [[ -f "batch_${i}.csv" ]]; then
        aws s3 cp batch_${i}.csv s3://tiktok-image-input/csv-files/parallel_${timestamp}_batch_${i}.csv --region us-east-2 &
        echo "📤 Uploading batch ${i}..."
    fi
done

# Wait for all uploads
wait

end_time=$(date +%s)
echo "=== ALL UPLOADS COMPLETED ==="
echo "Upload time: $((end_time - start_time)) seconds"
echo "🚀 10 Lambda instances processing simultaneously!"
echo "🎯 Expected completion: ~3 seconds"

# 3. Monitor all instances
aws logs tail /aws/lambda/image-collage-processor --follow --region us-east-2
```

### **Option 3: Creator-Based Split (Balanced)**

```bash
# 1. Extract each creator separately
echo "=== CREATING CREATOR-BASED BATCHES ==="

creators=("aaliahmaddox" "aal.i.jah" "aabjj81" "aaasisisiyou" "aaaer723" "aaliyah_garcia18" "aali.zm" "aalaysia_00" "aakritisubedi5" "aakritisadashanker" "aak9649")

for creator in "${creators[@]}"; do
    echo "creator_name,cover_url,created_at" > ${creator}.csv
    grep "^${creator}," cover_urls_20250819_104209.csv >> ${creator}.csv
    image_count=$(( $(wc -l < ${creator}.csv) - 1 ))
    echo "✅ ${creator}.csv: ${image_count} images"
done

# 2. Upload all creators simultaneously  
echo "=== PARALLEL CREATOR UPLOAD ==="
timestamp=$(date +%Y%m%d_%H%M%S)
start_time=$(date +%s)

for creator in "${creators[@]}"; do
    if [[ -f "${creator}.csv" ]]; then
        aws s3 cp ${creator}.csv s3://tiktok-image-input/csv-files/creator_${creator}_${timestamp}.csv --region us-east-2 &
        echo "📤 Uploading ${creator}..."
    fi
done

wait

end_time=$(date +%s)
echo "=== CREATOR UPLOAD COMPLETED ==="
echo "Upload time: $((end_time - start_time)) seconds"
echo "🚀 11 Lambda instances processing simultaneously!"
```

---

## 📊 **EXPECTED PERFORMANCE RESULTS**

### **Upload Performance:**
- **Sequential upload**: 1 file × 2.2 seconds = 2.2 seconds
- **Parallel upload**: 10 files × ~2.5 seconds = 2.5 seconds (minimal increase)

### **Processing Performance:**
- **Sequential processing**: 364 images ÷ 13 images/sec = 28 seconds
- **Parallel processing**: 38 images ÷ 13 images/sec = **3 seconds**

### **Total Time Comparison:**
- **Before**: 2.2s upload + 28s processing = **30.2 seconds**
- **After**: 2.5s upload + 3s processing = **5.5 seconds**
- **Speed Improvement**: **5.5x faster!**

---

## ⚠️ **IMPORTANT NOTES**

### **Lambda Concurrency Limits:**
- **Your current limit**: 10 concurrent executions
- **AWS default**: 1000 concurrent executions
- **To increase**: Submit AWS support request

### **Best Practices:**
1. **Always use `&` for parallel uploads**
2. **Always use `wait` to ensure completion**
3. **Monitor CloudWatch for errors**
4. **Clean up batch files after processing**

### **Troubleshooting:**
```bash
# If uploads fail, check AWS credentials
aws sts get-caller-identity

# If Lambda doesn't trigger, check S3 notifications
aws s3api get-bucket-notification-configuration --bucket tiktok-image-input --region us-east-2

# If processing fails, check Lambda logs
aws logs describe-log-streams --log-group-name /aws/lambda/image-collage-processor --region us-east-2
```

---

## 🚀 **SCALING TO 2M IMAGES**

### **Monthly Processing Strategy:**

```bash
# For 2M images with 10 concurrent limit:
# 2,000,000 ÷ 360 images per wave = 5,556 waves
# 5,556 waves × 3 seconds per wave = 16,668 seconds = 4.6 hours

# With 1000 concurrent limit (after increase):
# 2,000,000 ÷ 36,000 images per wave = 56 waves  
# 56 waves × 3 seconds per wave = 168 seconds = 2.8 minutes!
```

### **Production Implementation:**
1. **Split monthly data** into optimal batch sizes
2. **Process in waves** respecting concurrency limits
3. **Monitor costs** and performance
4. **Implement error recovery** for failed batches

---

**This guide shows you exactly how to achieve 5-9x speed improvement with parallel processing!**

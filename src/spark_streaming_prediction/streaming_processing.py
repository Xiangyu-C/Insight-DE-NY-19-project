from pyspark.ml.classification import RandomForestClassificationModel
from pyspark.sql import SparkSession, SQLContext, Row
from pyspark.sql.types import *
from pyspark.streaming import StreamingContext
from pyspark import SparkConf
from pyspark.streaming.kafka import KafkaUtils
from pyspark.ml.feature import VectorAssembler
from pyspark.sql.functions import col, create_map, lit
from itertools import chain
from cassandra.cluster import Cluster
from cassandra.util import uuid_from_time
from datetime import datetime
from json import loads
import json
import time
import os, boto


# Set up connection with S3
aws_access_key = os.getenv('AWS_ACCESS_KEY_ID', 'default')
aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY', 'default')
conn = boto.connect_s3(aws_access_key, aws_secret_access_key)
bk = conn.get_bucket('cyber-insight', validate=False)

# Create spark session
conf = SparkConf().set('spark.cassandra.connection.host', 'ec2-18-232-2-76.compute-1.amazonaws.com')   \
                  .set('spark.streaming.backpressure.enabled', True)  \
                  .set('spark.streaming.kafka.maxRatePerPartition', 500)
spark = SparkSession \
    .builder \
    .config(conf=conf)  \
    .appName("Real time prediction") \
    .master('spark://ip-10-0-0-14.ec2.internal:7077') \
    .getOrCreate()

sc = spark.sparkContext

a1 = sc.accumulator(0); t1 = sc.accumulator(0)
a2 = sc.accumulator(0); t2 = sc.accumulator(0)
a3 = sc.accumulator(0); t3 = sc.accumulator(0)
a4 = sc.accumulator(0); t4 = sc.accumulator(0)
a5 = sc.accumulator(0); t5 = sc.accumulator(0)
a6 = sc.accumulator(0); t6 = sc.accumulator(0)

kafka_topic = 'cyber'
ssc = StreamingContext(sc, 3)
#ssc.checkpoint('home/ubuntu/batch/cyber/')

kvs = KafkaUtils.createDirectStream(ssc, [kafka_topic],
                                    {'metadata.broker.list': 'ec2-54-80-57-187.compute-1.amazonaws.com:9092',
                                    'auto.offset.reset': 'smallest'})

# Connect to Cassandra DB for writing prediction results
cluster = Cluster(['ec2-18-232-2-76.compute-1.amazonaws.com'])
cass_session = cluster.connect('cyber_id')

# Get proper feature names
feature_list_all = ['Bwd Pkt Len Min',
                    'Subflow Fwd Byts',
                    'TotLen Fwd Pkts',
                    'Fwd Pkt Len Mean',
                    'Bwd Pkt Len Std',
                    'Flow IAT Mean',
                    'Fwd IAT Min',
                    'Flow Duration',
                    'Flow IAT Std',
                    'Active Min',
                    'Active Mean',
                    'Bwd IAT Mean',
                    'Fwd IAT Mean',
                    'Init Fwd Win Byts',
                    'Fwd PSH Flags',
                    'SYN Flag Cnt',
                    'Fwd Pkts/s',
                    'Init Bwd Win Byts',
                    'Bwd Pkts/s',
                    'PSH Flag Cnt',
                    'Pkt Size Avg',
                    'Label',
                    'Timestamp',
                    'Source',
                    'Destination'
                    ]

feature_list = ['Bwd Pkt Len Min',
                'Subflow Fwd Byts',
                'TotLen Fwd Pkts',
                'Fwd Pkt Len Mean',
                'Bwd Pkt Len Std',
                'Flow IAT Mean',
                'Fwd IAT Min',
                'Flow Duration',
                'Flow IAT Std',
                'Active Min',
                'Active Mean',
                'Bwd IAT Mean',
                'Fwd IAT Mean',
                'Init Fwd Win Byts',
                'Fwd PSH Flags',
                'SYN Flag Cnt',
                'Fwd Pkts/s',
                'Init Bwd Win Byts',
                'Bwd Pkts/s',
                'PSH Flag Cnt',
                'Pkt Size Avg'
                ]

labels_dict = {0: 'Benign',
               1: 'DDOS attack-HOIC',
               2: 'DDoS attacks-LOIC-HTTP',
               3: 'DoS attacks-Hulk',
               4: 'Bot',
               5: 'FTP-BruteForce',
               6: 'SSH-Bruteforce',
               7: 'Infilteration',
               8: 'DoS attacks-SlowHTTPTest',
               9: 'DoS attacks-GoldenEye',
              10: 'DoS attacks-Slowloris',
              11: 'Brute Force -Web',
              12: 'DDOS attack-LOIC-UDP'}

# Reload trained randomforest model from s3
rfc_model = RandomForestClassificationModel.load('s3n://cyber-insight/rfc_model_multi')
assembler_feats = VectorAssembler(inputCols=feature_list, outputCol='features')

def attacks_and_count_per_server(df, tl):
    """
    This function takes a dataframe returned by machine learning
    model and query it to find out two metrics:
    1. Attacks predicted per server per second
    2. Total traffic per server per second
    Then write to a Cassandra table
    """
    df.createOrReplaceTempView('results')
    # Get malicious predictions per server IP
    all_predictions = spark.sql("select Destination, count(*) as count from results \
                                 where prediction!=0 group by Destination order by Destination")
    # Get total traffic per server IP
    all_traffic = spark.sql("Select Destination, count(*) as count from results \
                             group by Destination order by Destination")

    if all_predictions.count()==13 and all_traffic.count()==13:
        # Collect values for attack predictions and also total visits per second
        s1a, s2a, s3a, s4a, s5a, s6a, s7a, s8a, s9a, s10a, s11a, s12a, s13a = \
        all_predictions.collect()

        s1t, s2t, s3t, s4t, s5t, s6t, s7t, s8t, s9t, s10t, s11t, s12t, s13t = \
        all_traffic.collect()
        # Calculate per second stats
        s1a=s1a[1]/tl; s2a=s2a[1]/tl; s3a=s3a[1]/tl; s4a=s4a[1]/tl; s5a=s5a[1]/tl; s6a=s6a[1]/tl; s7a=s7a[1]/tl
        s8a=s8a[1]/tl; s9a=s9a[1]/tl; s10a=s10a[1]/tl; s11a=s11a[1]/tl; s12a=s12a[1]/tl; s13a=s13a[1]/tl

        s1t=s1t[1]/tl; s2t=s2t[1]/tl; s3t=s3t[1]/tl; s4t=s4t[1]/tl; s5t=s5t[1]/tl; s6t=s6t[1]/tl; s7t=s7t[1]/tl
        s8t=s8t[1]/tl; s9t=s9t[1]/tl; s10t=s10t[1]/tl; s11t=s11t[1]/tl; s12t=s12t[1]/tl; s13t=s13t[1]/tl


        # Insert attacks per second into cassandra table
        cass_session.execute(
        """
        insert into count_attack (id, t, a, b, c, d, e, f, g, h, i, j, k, l, m)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        ('rate', uuid_from_time(datetime.now()), s1a, s2a, s3a, s4a, s5a, s6a,   \
                   s7a, s8a, s9a, s10a, s11a, s12a, s13a)                        \
        )

        # Insert traffic per second into cassandra table
        cass_session.execute(
        """
        insert into count_traffic (id, t, a, b, c, d, e, f, g, h, i, j, k, l, m)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        ('rate', uuid_from_time(datetime.now()), s1t, s2t, s3t, s4t, s5t, s6t,   \
                   s7t, s8t, s9t, s10t, s11t, s12t, s13t)                        \
        )
    else:
        pass

def convertColumn(df, names, newType):
  for name in names:
     df = df.withColumn(name, df[name].cast(newType))
  return(df)


def getSparkSessionInstance(sparkConf):
    '''
    Function to find spark session
    '''
    conf = SparkConf().set('spark.cassandra.connection.host',
                       'ec2-18-232-2-76.compute-1.amazonaws.com')  \
                      .set('spark.streaming.backpressure.enabled', True)  \
                      .set('spark.streaming.kafka.maxRatePerPartition', 500)
    if ("sparkSessionSingletonInstance" not in globals()):
        globals()["sparkSessionSingletonInstance"] = SparkSession \
            .builder \
            .config(conf=conf) \
            .getOrCreate()
    return globals()["sparkSessionSingletonInstance"]

def process(rdd):
	"""
	This function will process each RDD and convert to
	a dataframe, perform prediction and keep running
	totals using accumulators
	"""
    start = time.time()
    spark = getSparkSessionInstance(rdd.context.getConf())

    global a1; global a2; global a3
    global a4; global a5; global a6
    global t1; global t2; global t3
    global t4; global t5; global t6

    df = spark.read.json(rdd)
    df = convertColumn(df, feature_list, FloatType())
    new_data = assembler_feats.transform(df)
    predict = rfc_model.transform(new_data)
    test = predict.select(['Timestamp', 'Label', 'prediction', 'Source', 'Destination'])
    end = time.time()
    tl = end-start
    attacks_and_count_per_server(test, tl)

    mapping_expr = create_map([lit(x) for x in chain(*labels_dict.items())])
    test = test.withColumn('predicted_labels', mapping_expr.getItem(col('prediction')))
    correct_preds = test.where('predicted_labels in (Label)')
    top_6_preds = correct_preds.groupby('predicted_labels').count().orderBy('count', ascending=False).collect()[0:6]
    top_6_class = test.groupby('Label').count().orderBy('count', ascending=False).collect()[0:6]

    a1, a2, a3, a4, a5, a6 = a1.value+top_6_preds[0][1],    \
                             a2.value+top_6_preds[1][1],    \
                             a3.value+top_6_preds[2][1],    \
                             a4.value+top_6_preds[3][1],    \
                             a5.value+top_6_preds[4][1],    \
                             a6.value+top_6_preds[5][1]

    t1, t2, t3, t4, t5, t6 = t1.value+top_6_class[0][1],    \
                             t2.value+top_6_class[1][1],    \
                             t3.value+top_6_class[2][1],    \
                             t4.value+top_6_class[3][1],    \
                             t5.value+top_6_class[4][1],    \
                             t6.value+top_6_class[5][1]

    sum1 = a1+a2+a3+a4+a5+a6
    sum2 = t1+t2+t3+t4+t5+t6

    cass_session.execute(
        """
        insert into pred_accuracy (id, t, a1, a2, a3, a4, a5, a6, a7,
                                          t1, t2, t3, t4, t5, t6, t7)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        ('accu', uuid_from_time(datetime.now()), str(round(a1/t1*100, 1))+'%', str(round(a2/t2*100, 1))+'%', str(round(a3/t3*100, 1))+'%',     \
                                                 str(round(a4/t4*100, 1))+'%', str(round(a5/t5*100, 1))+'%', str(round(a6/t6*100, 1))+'%',     \
                                                 str(round(sum1/sum2*100, 1))+'%',       \
                                                 t1, t2, t3, t4, t5, t6, sum2) \
    )


    test.write \
          .format('org.apache.spark.sql.cassandra') \
          .mode('append') \
          .options(table='all_predictions', keyspace='cyber_id') \
          .save()

parsed_msg = kvs.map(lambda x: json.loads(x[1]))
parsed_msg.foreachRDD(process)

ssc.start()
ssc.awaitTermination()
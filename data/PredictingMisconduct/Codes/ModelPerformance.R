### Predicting Corruption (PGN Outcomes) ###
#install.packages("randomForest")
rm(list=ls())

## Preparation of data
library(caret)
library(ROCR)
library(SuperLearner)
library(pdp)
library(glmnet)
library(gbm)
library(ROSE)
library(tidyverse)
library(ggplot2)
library(randomForest)

# Add Folder
setwd("")


##########################################################################################
## LASSO 
##########################################################################################

## Outcome: corrupt
corruption <- read.csv("MainDatset.csv", sep="")
corruption <- corruption[ , -c(1, 1:2)]
corruption$corrupt <- factor(corruption$corrupt)

# Standardization
preprocessParams <- preProcess(corruption[,2:ncol(corruption)], method=c("center", "scale"))
corruption2 <- predict(preprocessParams, corruption[,2:ncol(corruption)])
corruption = as.data.frame(cbind(corrupt = corruption$corrupt, corruption2))
rm(corruption2)

# Training and Test Samples
set.seed(123)
train_sample <- sample(nrow(corruption), round(nrow(corruption)*0.7))
corruption_train <- corruption[train_sample, ]
corruption_test <- corruption[-train_sample, ]

## Cross-Validated Neural Network 
ctrl <- trainControl(method = "repeatedcv", number=5, repeats=10)

tuneGrid=expand.grid(.alpha=seq(from = 0, to = 1, by = 0.5),
                     .lambda=10^seq(10,-3,length=50))

corruption_lasso <- train(corrupt ~ ., data = corruption_train, method = "glmnet",
                          metric = "Accuracy", trControl = ctrl,
                          tuneGrid = tuneGrid)

corruption_lasso

#### Performance measures
# Sensitivity/Specificity/Accuracy/Precision (Pos Pred Value)
corruption_pred_lasso <- predict(corruption_lasso, corruption_test)
confusionMatrix(corruption_test$corrupt, corruption_pred_lasso, positive="1")

# ROC and AUC
corruption_predlasso_prob <- predict(corruption_lasso, corruption_test, type="prob")
corruption_predlasso_prob <- corruption_predlasso_prob[, -1]
pred_lasso <- prediction(predictions = corruption_predlasso_prob, labels = corruption_test$corrupt)
perf_lasso <- performance(pred_lasso, measure = "tpr", x.measure = "fpr")
plot(perf_lasso, main = "ROC curve for corruption LASSO model",col = "blue", lwd = 3)

# AUC
perf.auc_lasso <- performance(pred_lasso, measure = "auc")
unlist(perf.auc_lasso@y.values)


# Predict
X <- read.csv("MainDatset.csv", sep="")
ID <- X[,c(1:2)]
X <- X[ , -c(1, 1:3)]
preprocessParams <- preProcess(X, method=c("center", "scale"))
X <- predict(preprocessParams, X)

p <- predict(corruption_lasso, X, type="prob",
             norm.votes=TRUE)
p <- p[ , -c(1:1)]
Data <- cbind(ID, p)
write.csv(Data,"lassoPrediction.csv", row.names = TRUE)

p1 <- coef(corruption_lasso)

# Variable Importance
rfImp <- varImp(corruption_lasso, corruption_lasso$bestTune$lambda)
plot(rfImp, top = 10, main="LASSO")
top10 <- rfImp[["importance"]]

yy <- coef(corruption_lasso$finalModel, corruption_lasso$bestTune$lambda)
zz <- unlist(yy@Dimnames[1])
coeflasso <- cbind(zz[yy@i],yy@x)


##########################################################################################
## RANDOM FOREST -- UNBALANCED
##########################################################################################
## Outcome: corrupt
corruption <- read.csv("MainDatset.csv", sep="")
corruption <- corruption[ , -c(1, 1:2)]
corruption$corrupt <- factor(corruption$corrupt)


# Standardization
preprocessParams <- preProcess(corruption[,2:ncol(corruption)], method=c("center", "scale"))
corruption2 <- predict(preprocessParams, corruption[,2:ncol(corruption)])
corruption = as.data.frame(cbind(corrupt = corruption$corrupt, corruption2))
rm(corruption2)

# Training and Test Samples
set.seed(123)
train_sample <- sample(nrow(corruption), round(nrow(corruption)*0.7))
corruption_train <- corruption[train_sample, ]
corruption_test <- corruption[-train_sample, ]

## Cross-Validated Random Forest for corrupt

set.seed(123)

ctrl <- trainControl(method = "repeatedcv", number=5, repeats=10)

grid_rf <- expand.grid(.mtry = c(round(sqrt(ncol(corruption)-1)/4), round(sqrt(ncol(corruption)-1)/3), round(sqrt(ncol(corruption)-1)/2), 
                                 round(sqrt(ncol(corruption)-1)), round(sqrt(ncol(corruption)-1))*2))

corruption_rf <- train(corrupt ~ ., data = corruption_train, method = "rf",
                       metric = "Accuracy", trControl = ctrl,
                       ntree = 500,
                       tuneGrid = grid_rf)

corruption_rf

# Performance Measures
corruption_pred_rf <- predict(corruption_rf, corruption_test)
confusionMatrix(corruption_test$corrupt, corruption_pred_rf, positive="1")

# ROC and AUC
corruption_predrf_prob <- predict(corruption_rf, corruption_test, type="prob")
corruption_predrf_prob <- corruption_predrf_prob[, -1]
pred_rf <- prediction(predictions = corruption_predrf_prob, labels = corruption_test$corrupt)
perf_rf <- performance(pred_rf, measure = "tpr", x.measure = "fpr")
plot(perf_rf, main = "ROC curve for corruption random forests model",col = "blue", lwd = 3)

perf.auc_rf <- performance(pred_rf, measure = "auc")
unlist(perf.auc_rf@y.values)

# Precision, recall, F1-Score
precision_rf <- posPredValue(corruption_pred_rf, corruption_test$corrupt, positive = "1")
recall_rf <- sensitivity(corruption_pred_rf, corruption_test$corrupt, positive = "1")
f1_rf <- (2 * precision_rf * recall_rf) / (precision_rf + recall_rf)
f1_rf

# Predict
X <- read.csv("MainDatset.csv", sep="")
ID <- X[,c(1:2)]
X <- X[ , -c(1, 1:3)]
preprocessParams <- preProcess(X, method=c("center", "scale"))
X <- predict(preprocessParams, X)

p <- predict(corruption_rf, X, type="prob",
             norm.votes=TRUE)
p <- p[ , -c(1:1)]
Data <- cbind(ID, p)
#write.csv(Data,"RFPrediction.csv", row.names = TRUE)

# Variable Importance
rfImp <- varImp(corruption_rf)
plot(rfImp, top = 10, main="Random Forest")
top10 <- rfImp[["importance"]]



##########################################################################################
## GBM -- UNBALANCED
##########################################################################################
## Outcome: corrupt
corruption <- read.csv("MainDatset.csv", sep="")
corruption <- corruption[ , -c(1, 1:2)]
corruption$corrupt <- factor(corruption$corrupt)

# Standardization
preprocessParams <- preProcess(corruption[,2:ncol(corruption)], method=c("center", "scale"))
corruption2 <- predict(preprocessParams, corruption[,2:ncol(corruption)])
corruption = as.data.frame(cbind(corrupt = corruption$corrupt, corruption2))
rm(corruption2)

# Training and Test Samples
set.seed(123)
train_sample <- sample(nrow(corruption), round(nrow(corruption)*0.7))
corruption_train <- corruption[train_sample, ]
corruption_test <- corruption[-train_sample, ]

ctrl <- trainControl(method = "repeatedcv", number=5, repeats=10)

GBMGrid <- expand.grid(interaction.depth=c(5, 7, 9, 11), n.trees = c(100, 150, 200, 250, 300, 350),
                       shrinkage=c(0.01, 0.001),
                       n.minobsinnode=c(10))

corruption_gbm <- train(corrupt~., data = corruption_train, 
                        method = "gbm", 
                        tuneGrid=GBMGrid,
                        trControl=ctrl, verbose=FALSE)

corruption_gbm

#### Performance measures
# Sensitivity/Specificity/Accuracy/Precision (Pos Pred Value)
corruption_pred_gbm <- predict(corruption_gbm, corruption_test)
confusionMatrix(corruption_test$corrupt, corruption_pred_gbm, positive="1")

# ROC and AUC
corruption_predgbm_prob <- predict(corruption_gbm, corruption_test, type="prob")
corruption_predgbm_prob <- corruption_predgbm_prob[, -1]
pred_gbm <- prediction(predictions = corruption_predgbm_prob, labels = corruption_test$corrupt)
perf_gbm <- performance(pred_gbm, measure = "tpr", x.measure = "fpr")
plot(perf_gbm, main = "ROC curve for corruption GBM model",col = "blue", lwd = 3)

perf.auc_gbm <- performance(pred_gbm, measure = "auc")
unlist(perf.auc_gbm@y.values)

# Predict
X <- read.csv("MainDatset.csv", sep="")
ID <- X[,c(1:2)]
X <- X[ , -c(1, 1:3)]
preprocessParams <- preProcess(X, method=c("center", "scale"))
X <- predict(preprocessParams, X)

p <- predict(corruption_gbm, X, type="prob",
             norm.votes=TRUE)
p <- p[ , -c(1:1)]
Data <- cbind(ID, p)
write.csv(Data,"GBMPrediction.csv", row.names = TRUE)

# Variable Importance
rfImp <- varImp(corruption_gbm)
plot(rfImp, top = 10, main="GBM")
top10 <- rfImp[["importance"]]


##########################################################################################
## NEURAL NETWORKS -- UNBALANCED
##########################################################################################

## Outcome: corrupt
corruption <- read.csv("MainDatset.csv", sep="")
corruption <- corruption[ , -c(1, 1:2)]
corruption$corrupt <- factor(corruption$corrupt)

# Standardization
preprocessParams <- preProcess(corruption[,2:ncol(corruption)], method=c("center", "scale"))
corruption2 <- predict(preprocessParams, corruption[,2:ncol(corruption)])
corruption = as.data.frame(cbind(corrupt = corruption$corrupt, corruption2))
rm(corruption2)

# Training and Test Samples
set.seed(123)
train_sample <- sample(nrow(corruption), round(nrow(corruption)*0.7))
corruption_train <- corruption[train_sample, ]
corruption_test <- corruption[-train_sample, ]

## Cross-Validated Neural Network 
ctrl <- trainControl(method = "repeatedcv", number=5, repeats=10)

grid_nn <-  expand.grid(size = seq(from = 1, to = 2, by = 1),
                        decay = seq(from = 0.9, to = 0.99, by = 0.03))


corruption_nn <- train(corrupt~., data=corruption_train, method="nnet", 
                       trControl=ctrl,
                       tuneGrid = grid_nn, 
                       maxit = 500, 
                       metric = "Accuracy")

corruption_nn

# Performance Measures
corruption_pred_nn <- predict(corruption_nn, corruption_test)
confusionMatrix(corruption_test$corrupt, corruption_pred_nn, positive="1")

# ROC and AUC
corruption_prednn_prob <- predict(corruption_nn, corruption_test, type="prob")
corruption_prednn_prob <- corruption_prednn_prob[, -1]
pred_nn <- prediction(predictions = corruption_prednn_prob, labels = corruption_test$corrupt)
perf_nn <- performance(pred_nn, measure = "tpr", x.measure = "fpr")
plot(perf_nn, main = "ROC curve for corruption Neural Network model",col = "blue", lwd = 3)

perf.auc_nn <- performance(pred_nn, measure = "auc")
unlist(perf.auc_nn@y.values)

# Predict
X <- read.csv("MainDatset.csv", sep="")
ID <- X[,c(1:2)]
X <- X[ , -c(1, 1:3)]
preprocessParams <- preProcess(X, method=c("center", "scale"))
X <- predict(preprocessParams, X)

p <- predict(corruption_nn, X, type="prob",
             norm.votes=TRUE)
p <- p[ , -c(1:1)]
Data <- cbind(ID, p)
write.csv(Data,"NNPrediction.csv", row.names = TRUE)

# Variable Importance
rfImp <- varImp(corruption_nn)
plot(rfImp, top = 10, main="Neural Network")
top10 <- rfImp[["importance"]]
# Variable Importance
rfImp <- varImp(corruption_nn)
plot(rfImp, top = 10, main="Neural Network")
top10 <- rfImp[["importance"]]


##########################################################################################
## Super Learner -- UNBALANCED
##########################################################################################
## Outcome: corrupt
corruption <- read.csv("MainDatset.csv", sep="")
corruption <- corruption[ , -c(1, 1:2)]
corruption$corrupt <- factor(corruption$corrupt)

# Standardization
preprocessParams <- preProcess(corruption[,2:ncol(corruption)], method=c("center", "scale"))
corruption2 <- predict(preprocessParams, corruption[,2:ncol(corruption)])
corruption = as.data.frame(cbind(corrupt = corruption$corrupt, corruption2))
rm(corruption2)

# Training and Test Samples
set.seed(123)
train_sample <- sample(nrow(corruption), round(nrow(corruption)*0.7))
corruption_train <- corruption[train_sample, ]
corruption_test <- corruption[-train_sample, ]
corruption_train$corrupt <- as.numeric(corruption_train$corrupt)-1
corruption_test$corrupt <- as.numeric(corruption_test$corrupt)-1

set.seed(123)


SL.rf1 <- function(...,method="rf", trControl=trainControl(method = "repeatedcv", number=5, repeats=10), 
                   tuneGrid=expand.grid(.mtry = c(round(sqrt(ncol(corruption)-1)/4),
                                                  round(sqrt(ncol(corruption)-1)/3),
                                                  round(sqrt(ncol(corruption)-1)/2), 
                                                  round(sqrt(ncol(corruption)-1))))){
  SL.caret(...,method=method,trControl=trControl,tuneGrid=tuneGrid) 
}


SL.gbm1 <- function(...,method="gbm", trControl=trainControl(method = "repeatedcv", number=5, repeats=10),
                    tuneGrid=expand.grid(interaction.depth=c(1, 3, 5, 7), 
                                         n.trees = c(50, 100, 150, 200, 250, 300),
                                         shrinkage=c(0.01, 0.001),
                                         n.minobsinnode=10)){
  SL.caret(...,method=method,trControl=trControl,tuneGrid=tuneGrid)
}

SL.nnet1 <- function(...,method="nnet", trControl=trainControl(method = "repeatedcv", number=5, repeats=10),
                     tuneGrid=expand.grid(size = seq(from = 1, to = 2, by = 1),
                                          decay = seq(from = 0.9, to = 0.99, by = 0.03))){
  SL.caret(...,method=method,trControl=trControl,tuneGrid=tuneGrid) 
}

SL.lasso1 <- function(...,method="glmnet", trControl=trainControl(method = "repeatedcv", number=5, repeats=10), 
                      tuneGrid=expand.grid(.alpha=seq(from = 0, to = 1, by = 0.5),
                                           .lambda=10^seq(10,-3,length=50))){
  SL.caret(...,method=method,trControl=trControl,tuneGrid=tuneGrid) 
}

set.seed(123)

corrupt_sl <- SuperLearner(Y = corruption_train$corrupt, X = corruption_train[,-1], family = binomial(),
                           SL.library = c("SL.rf1", "SL.gbm1", "SL.nnet1", "SL.lasso1"))

corrupt_sl

# Performance Measures
pred <- predict(corrupt_sl, corruption_test[,-1], onlySL = T)
corruption_pred_sl <- ifelse(pred$pred>0.5, 1, 0)

corruption_train$corrupt <- factor(corruption_train$corrupt)
corruption_test$corrupt <- factor(corruption_test$corrupt)
corruption_pred_sl <- factor(corruption_pred_sl)

confusionMatrix(corruption_test$corrupt, corruption_pred_sl, positive="1")


# ROC and AUC
corruption_predsl_prob <- pred$pred
pred_sl <- prediction(predictions = corruption_predsl_prob, labels = corruption_test$corrupt)
perf_sl <- performance(pred_sl, measure = "tpr", x.measure = "fpr")
plot(perf_sl, main = "ROC curve for Super Learning ensemble model",col = "blue", lwd = 3)

perf.auc_sl <- performance(pred_sl, measure = "auc")
unlist(perf.auc_sl@y.values)

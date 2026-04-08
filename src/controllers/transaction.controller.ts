import { Request, Response, NextFunction } from 'express';
import { TransactionService } from '../services/transaction.service';

const service = new TransactionService();

export const createTransaction = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userRole = req.user!.role;
    const userId = req.user!.sub;

    const transaction = await service.createTransaction(userId, userRole, req.body);
    res.status(201).json({
      status: 'success',
      data: transaction,
    });
  } catch (error: any) {
    if (error.status) {
      res.status(error.status).json({ status: 'error', message: error.message });
      return;
    }
    next(error);
  }
};

export const getTransactions = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userRole = req.user!.role;
    const userId = req.user!.sub;

    // query is validated by previous middleware mapping to `transactionQuerySchema`
    const paginatedResult = await service.getTransactions(userId, userRole, req.query as any);
    
    res.status(200).json({
      status: 'success',
      data: paginatedResult.data,
      meta: paginatedResult.meta,
    });
  } catch (error: any) {
    next(error);
  }
};

export const getTransaction = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userRole = req.user!.role;
    const userId = req.user!.sub;
    const transactionId = req.params.id as string;

    const transaction = await service.getTransactionById(userId, userRole, transactionId);
    res.status(200).json({
      status: 'success',
      data: transaction,
    });
  } catch (error: any) {
    if (error.status) {
      res.status(error.status).json({ status: 'error', message: error.message });
      return;
    }
    next(error);
  }
};

export const updateTransaction = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userRole = req.user!.role;
    const userId = req.user!.sub;
    const transactionId = req.params.id as string;

    const transaction = await service.updateTransaction(userId, userRole, transactionId, req.body);
    res.status(200).json({
      status: 'success',
      data: transaction,
    });
  } catch (error: any) {
    if (error.status) {
      res.status(error.status).json({ status: 'error', message: error.message });
      return;
    }
    next(error);
  }
};

export const deleteTransaction = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userRole = req.user!.role;
    const userId = req.user!.sub;
    const transactionId = req.params.id as string;

    await service.deleteTransaction(userId, userRole, transactionId);
    
    // Deletion responds with 204 No Content typically, or 200 with success message
    res.status(200).json({
      status: 'success',
      message: 'Transaction successfully deleted.',
    });
  } catch (error: any) {
    if (error.status) {
      res.status(error.status).json({ status: 'error', message: error.message });
      return;
    }
    next(error);
  }
};

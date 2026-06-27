package com.demo.repository;

@Repository
public interface CustomerRepository {
    String findById(String id);
}

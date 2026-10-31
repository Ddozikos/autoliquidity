def prioritize(car,min_price=300000,min_demand=70):
 return car.doc_type=='ban' and car.status!='В залоге' and car.price is not None and car.demand is not None and car.price>=min_price and car.demand>=min_demand
